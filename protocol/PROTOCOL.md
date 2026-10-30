# Sync box protocol (version 1)

USB serial, 115200 baud, ASCII, one message per line, `\n` terminated.
Format: `<TYPE> <fields...>*<CRC>` where `<CRC>` is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
over the bytes before `*`, as four upper-case hex digits.

## Box → PC (every message carries one shared 32-bit sequence number `seq`, starting at 0 at boot)

| Line | Meaning |
|---|---|
| `C seq t_us interval_us` | Switch closure accepted. `t_us` = box microsecond timer at the closure. `interval_us` since the previous accepted closure (0 for the first). |
| `B seq t_us` | Closure rejected as contact bounce (within the debounce time of the previous accepted closure). |
| `T seq t_us req_id` | Reply to a time request: `t_us` is the box time when the request was processed. |
| `H seq t_us fw_version serial` | Hello: sent on connect, every second, and in answer to `I`. `serial` is the board's unique ID. |

A gap or repeat in `seq` is a fault on the PC side. The box never skips a number.

## PC → box

| Line | Meaning |
|---|---|
| `T req_id` | Time request. The box answers with `T` carrying the same `req_id`. |
| `D us` | Set the debounce time in microseconds (default 20000). |
| `I` | Identify: the box answers with `H`. |
