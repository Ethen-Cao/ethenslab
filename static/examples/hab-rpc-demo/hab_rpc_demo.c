#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <habmm.h>

#define WIRE_SIZE 20u
#define MAGIC 0x48414231u
static volatile sig_atomic_t stopping;
static void on_signal(int sig) { (void)sig; stopping = 1; }
static uint64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return (uint64_t)t.tv_sec * 1000u + (uint64_t)t.tv_nsec / 1000000u;
}
static void pause_ms(unsigned ms)
{
    struct timespec t = { ms / 1000u, (long)(ms % 1000u) * 1000000L };
    (void)nanosleep(&t, NULL);
}
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | p[3];
}
static unsigned number(const char *s, unsigned max)
{
    char *end; unsigned long n;
    errno = 0; n = strtoul(s, &end, 10);
    if (errno || !*s || *end || *s == '-' || n > max) {
        fprintf(stderr, "invalid number: %s\n", s); exit(2);
    }
    return (unsigned)n;
}
static int send_packet(int32_t h, uint8_t *b)
{
    uint64_t end = now_ms() + 2000;
    while (!stopping && now_ms() < end) {
        int r = habmm_socket_send(h, b, WIRE_SIZE,
                                 HABMM_SOCKET_SEND_FLAGS_NON_BLOCKING);
        if (r != -EAGAIN) return r;
        pause_ms(10);
    }
    return stopping ? -EINTR : -ETIMEDOUT;
}
static int recv_packet(int32_t h, uint8_t *b)
{
    uint32_t n = WIRE_SIZE; /* Reset capacity before every receive. */
    int r = habmm_socket_recv(h, b, &n, 200, HABMM_SOCKET_RECV_FLAGS_TIMEOUT);
    if (r) return r; /* EOVERFLOW: retained packet; caller closes the channel. */
    return n == WIRE_SIZE && get32(b) == MAGIC && get32(b + 4) == 1 ? 0 : -EPROTO;
}
static int session(int32_t h, int server, uint32_t *next_id)
{
    uint8_t b[WIRE_SIZE];
    while (!stopping) {
        int r; uint32_t id;
        if (server) {
            r = recv_packet(h, b);
            if (r == -ETIMEDOUT || r == -EAGAIN) continue;
            if (r) return r;
            if (get32(b + 8) != 1) return -EPROTO;
            put32(b + 8, 2); put32(b + 16, get32(b + 16) + 1u);
            r = send_packet(h, b);
        } else {
            id = (*next_id)++; /* New request; never replay an uncertain request. */
            put32(b, MAGIC); put32(b + 4, 1); put32(b + 8, 1);
            put32(b + 12, id); put32(b + 16, 41);
            r = send_packet(h, b);
            if (!r) {
                uint64_t end = now_ms() + 2000;
                do { r = recv_packet(h, b); }
                while (!stopping && now_ms() < end &&
                       (r == -ETIMEDOUT || r == -EAGAIN));
            }
            if (!r && (get32(b + 8) != 2 || get32(b + 12) != id ||
                       get32(b + 16) != 42)) r = -EPROTO;
            if (!r) { printf("request=%" PRIu32 " result=42\n", id); fflush(stdout); }
        }
        if (r) return r;
        if (!server) pause_ms(250);
    }
    return -EINTR;
}
int main(int argc, char **argv)
{
    unsigned minor, seconds; int server, r = 0; uint32_t next_id = 1;
    struct sigaction sa = { .sa_handler = on_signal };
    struct itimerval timer = {0};
    if ((argc != 3 && argc != 4) ||
        (strcmp(argv[1], "server") && strcmp(argv[1], "client"))) {
        fprintf(stderr, "usage: %s server|client assigned-minor [seconds]\n", argv[0]);
        return 2;
    }
    server = !strcmp(argv[1], "server"); minor = number(argv[2], 255);
    seconds = argc == 4 ? number(argv[3], 3600) : 30;
    if (!seconds) return 2;
    sigemptyset(&sa.sa_mask); /* No SA_RESTART: blocking waits remain interruptible. */
    if (sigaction(SIGINT, &sa, NULL) || sigaction(SIGTERM, &sa, NULL) ||
        sigaction(SIGALRM, &sa, NULL)) { perror("sigaction"); return 1; }
    timer.it_value.tv_sec = seconds; timer.it_interval.tv_usec = 200000;
    if (setitimer(ITIMER_REAL, &timer, NULL)) { perror("setitimer"); return 1; }
    while (!stopping) {
        int32_t h = 0;
        r = habmm_socket_open(&h, HAB_MMID_CREATE(MM_MISC, minor), 500,
                             HABMM_SOCKET_OPEN_FLAGS_SINGLE_BE_SINGLE_FE);
        if (!r) {
            if (!stopping) r = session(h, server, &next_id);
            int close_r = habmm_socket_close(h);
            if (close_r) { fprintf(stderr, "close: %d\n", close_r); return 1; }
        }
        if (!stopping && r) fprintf(stderr, "channel: %d; reopening\n", r);
        if (!stopping) pause_ms(100);
    }
    return 0;
}
