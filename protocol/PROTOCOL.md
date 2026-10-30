# Sync box protocol (version 1)

USB serial, 115200 baud, ASCII, one message per line, `\n` terminated.
Format: `<TYPE> <fields...>*<CRC>` where `<CRC>` is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
over the bytes before `*`, as four upper-case hex digits. Fields are separated by exactly one
space.

## Field types

| Field | Type |
|---|---|
| `seq` | 32-bit unsigned counter, decimal. One counter shared by every Box → PC message. The box increments it **before** sending, so the first message after boot carries `1`. After `4294967295` (2**32 - 1) it wraps to `0`. |
| `t_us` | Microseconds since the box booted, decimal, from a **64-bit** counter that never wraps (the firmware must use the Pico's 64-bit timer, `time_us_64()`, not the 32-bit one, which wraps after 71 minutes). Range 0 to 2**64 - 1. |
| `interval_us` | Microseconds between this accepted closure and the previous accepted one, decimal, 0 for the first. Same range as `t_us`. |
| `req_id` | 32-bit unsigned, decimal, chosen by the PC and echoed by the box. |
| `fw_version`, `serial` | Printable ASCII (0x21 to 0x7E), at least one character, with **no spaces and no `*`**. |

All numbers are non-negative decimal integers.

## Box → PC

| Line | Meaning |
|---|---|
| `C seq t_us interval_us` | Switch closure accepted. `t_us` = box time at the closure. |
| `B seq t_us` | Closure rejected as contact bounce (within the debounce time of the previous accepted closure). |
| `T seq t_us req_id` | Reply to a time request: `t_us` is the box time when the request was processed. |
| `H seq t_us fw_version serial` | Hello: sent on connect, every second, and in answer to `I`. `serial` is the board's unique ID. |

A gap or repeat in `seq` is a fault on the PC side. The box never skips a number.

## What the PC checks

The PC checks every line: the CRC, the message type, the number of fields, that every number is
a decimal integer within the range above, that the text fields follow the rule above, that `seq`
is exactly one more than the previous message's (mod 2**32), and that a `T` reply answers a
request the PC actually sent. **A line that fails any check is discarded and is a fault** (the
segment being recorded stops). The firmware must therefore never send a line it would not pass
itself.

If no line arrives for 3 seconds, or the serial port fails, that is a sync box fault.

## PC → box

| Line | Meaning |
|---|---|
| `T req_id` | Time request. The box answers with `T` carrying the same `req_id`. |
| `D us` | Set the debounce time in microseconds (default 20000). |
| `I` | Identify: the box answers with `H`. |
