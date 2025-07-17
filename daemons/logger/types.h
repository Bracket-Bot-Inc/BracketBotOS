#ifndef TYPES_H
#define TYPES_H

#include <stdint.h>
#include <stdbool.h>

typedef struct __attribute__((packed)) {
    uint8_t stereo[720][2560][3];
    double timestamp;
} camera_stereo_OV9281_t;

typedef struct __attribute__((packed)) {
    float yaw;
    float twist[2];
    double timestamp;
} drive_ctrl_t;

typedef struct __attribute__((packed)) {
    float pos[2];
    float vel[2];
    float torque[2];
    double timestamp;
} drive_state_t;

typedef struct __attribute__((packed)) {
    float voltage;
    double timestamp;
} drive_status_t;

typedef struct __attribute__((packed)) {
    float gyro[3];
    float accel[6];
    double timestamp;
} imu_t;

#endif /* TYPES_H */
