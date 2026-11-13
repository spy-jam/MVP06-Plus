# MVP 06 NCAA Baseball: PS2 vs Xbox dynasty save notes

Built from one pair of fresh (preseason) dynasties named "Matched", one made on each platform. The two
dynasties were created separately: college rosters are randomly generated, so player names and many values
differ. Layouts were compared using structure (names at the same offsets, identical "Default" rows, identical
tables), not by expecting equal bytes.

## Files
- PS2 `.psu`: folder `BASLUS-21367D...` with `icon.sys`, `title.ico`, an 8-byte marker file and `<name>.sav`.
  `.sav` = 0xC8-byte header + 0x176800-byte payload. Header starts with 4 x u32 LE checksums, using the same
  EA CRC as the GameCube MVP 2005 saves (`gc_checksums.ea_crc`):
  [header 0x10..0xC8, payload, title.ico, icon.sys]. Then 4 x u32 sizes and the UTF-16 name and type.
- Xbox `data.dat`: same container as MVP 2005 (two HMAC-SHA1, key = 16 zero bytes in the recomp; header
  0x50..0x108), payload 0x212800 bytes.
- Payload filler after the stream end: 0x55 at even offsets and 0xAA at odd ones, on both platforms. Old
  heap contents may sit inside it; they are ignored.

## Stream
Both platforms are little-endian, and bitfields pack LSB-first on both. Same stream on both: 7 `0xBEEFF00D`
markers and 22 tables tagged `F58F3C1B`. Sections that differ in layout (PS2 = C struct with padding, Xbox =
packed field by field):

| Where | PS2 | Xbox | Conversion |
|---|---|---|---|
| header 0xF0 | u8 + 3 pad, char[32] roster name | u8, char[32] | copy fields |
| header after name | 20 x u32 settings | 18 x u32 | kept from target template (which 2 are extra is not determined) |
| marker 1 + 0x12D4 | 16 conference records of 0x98 B: u8 id, char[13] short name, 136 B, 2 pad | u32 id, char[12] short name, 136 B | per field |
| marker 1 + 0x1B1C7 | 2 lists: u8 flag, 3 pad, u32 n, n x u32 | u8 flag, u32 n, n x u32 | drop/add pad |
| marker 2 + 0x195A0 | 16 B record (a, b, c, d) | (c, a, b, d) | reorder |
| end of schedule section | 18 bytes longer (all zero in these saves) | | zero-pad/trim; the converter stops if non-zero |
| stream end marker | value = its offset + 4 | same | recomputed |

Everything else is identical in layout and copied byte for byte. That covers all 22 tables, including the
3250 x 84 B player rows, the user section (marker 3/4) and history (marker 5, empty in fresh dynasties).

Checks: PS2 -> Xbox -> PS2 and Xbox -> PS2 -> Xbox give back the original data exactly. Every marker in a
converted file lands at the same offset as in the real save of that platform. Only tags 4 and 14 move: they
sit inside key lists and depend on content. Both containers verify.

## Open
- In-game tests: pending (PCSX2 and the recomp).
- Only fresh dynasties were seen. Mid-season data (schedule results, the 18-byte tail, history rows, and
  anything the season fills in) may use more padded fields. A mid-season save from each platform is needed to
  check this.
- The dynasty keeps the template's name.

## Roster saves
A roster save is 0xF7800 B of payload on both platforms (PS2 .sav 1,013,960 B with its 0xC8 header; Xbox data.dat
1,014,024 B). Its stream is a dynasty's section 2 on its own: it starts at the word after the dynasty's marker 1 and
ends with one closing marker (0xBEEFF00D, then its own offset + 4), then filler. The conferences sit at 0x12D0 and the
two lists at 0x1B1C3 (the dynasty offsets less 4), with the same PS2/Xbox differences. Checked on the default rosters
saved on each platform: after `roster_p2x`, the only bytes that differ are the randomly generated player names
(0x253FD to 0x675EF). The PS2 save had 16 stale bytes inside its trailing filler (0xF72D0), which aren't data.
