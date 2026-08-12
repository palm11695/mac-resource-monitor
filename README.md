# mac-resource-monitor

เก็บ log การใช้ CPU / RAM / Swap ของเครื่อง Mac อัตโนมัติ พร้อม dashboard สด
และรายงาน HTML แบบ static ไว้วิเคราะห์ย้อนหลัง — Python stdlib ล้วน
ไม่มี dependency, ไม่ต้องใช้ root

## ติดตั้ง

```bash
./install.sh
```

สคริปต์จะ generate LaunchAgent plist จาก path ของเครื่องคุณเอง ติดตั้งไว้ที่
`~/Library/LaunchAgents/` แล้วเริ่มทำงานทันที (และทุกครั้งที่ login):
ตัวเก็บข้อมูล (`sampler.py`) กับ dashboard server (`server.py`)
ที่ <http://127.0.0.1:8737>

## Config (env var ตอนรัน install.sh)

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `RESMON_LABEL` | `local.resmon` | prefix ของ launchd label |
| `RESMON_PYTHON` | `python3` ตัวแรกใน PATH | python ที่ใช้รัน |
| `RESMON_INTERVAL` | `10` | เก็บข้อมูลทุกกี่วินาที |
| `RESMON_HOST` | `127.0.0.1` | address ที่ dashboard ผูก (localhost เท่านั้นโดย default) |
| `RESMON_PORT` | `8737` | พอร์ตของ dashboard |
| `RESMON_LOG_DIR` | `<repo>/logs` | ที่เก็บไฟล์ CSV (อ่านโดย sampler/report ตอนรัน) |
| `RESMON_RETENTION_DAYS` | `90` | เก็บ log กี่วันก่อนลบอัตโนมัติ |

ตัวอย่าง: `RESMON_INTERVAL=30 RESMON_PORT=9000 ./install.sh`
(รัน install.sh ซ้ำได้เลยเมื่ออยากเปลี่ยนค่า — จะ reload agent ให้เอง)

## ส่วนประกอบ

| ไฟล์ | หน้าที่ |
|---|---|
| `sampler.py` | daemon เก็บข้อมูล (รันโดย launchd) |
| `server.py` | dashboard server — refresh อัตโนมัติ เลือกช่วง/interval ได้ |
| `report.py` | สร้างรายงาน static `report.html` (server ใช้ renderer ตัวเดียวกันนี้) |
| `install.sh` / `uninstall.sh` | ติดตั้ง/ถอน LaunchAgents |
| `logs/sys-YYYY-MM-DD.csv` | ข้อมูลระดับเครื่อง: CPU%, load, RAM breakdown, swap, swap/compressor I/O rate |
| `logs/proc-YYYY-MM-DD.csv` | top 5 process ตาม CPU และตาม RAM ต่อ tick |

### คอลัมน์ใน `sys-*.csv`

| คอลัมน์ | ความหมาย |
|---|---|
| `cpu_pct` | % ของ CPU ทั้งเครื่อง คิดจาก cputime delta (ดู "วิธีวัด") |
| `mem_used_mb` | active + wired + compressor (= "Memory Used" ใน Activity Monitor) |
| `mem_compressed_mb` | ขนาดที่ compressor กินอยู่ — **ตัวชี้ memory pressure ที่ไวที่สุด** |
| `mem_wired_mb` / `mem_free_mb` | wired (ย้ายไม่ได้) / free + inactive + speculative |
| `swap_used_mb` | ขนาด swap ที่ถูกใช้ (ระดับ ไม่ใช่อัตรา) |
| `swapin_mbs` / `swapout_mbs` | **อัตรา** อ่าน/เขียน swap MB/s ในช่วง tick นั้น |
| `compress_mbs` / `decompress_mbs` | อัตราบีบอัด/คลายบีบ MB/s |

คู่ `swapin/swapout` กับ `compress/decompress` คือตัวแยกระหว่าง "swap สูงแต่จอดนิ่ง"
(ไม่กระทบความเร็ว) กับ "กำลัง thrash" (กิน CPU + เขียน SSD ตลอด) — ดูจากระดับ
`swap_used_mb` อย่างเดียวแยกสองกรณีนี้ไม่ได้

ถ้า schema เปลี่ยนในอนาคต ไฟล์เดิมของวันนั้นจะถูกเปลี่ยนชื่อเป็น `.vN.csv`
แทนการเขียนต่อท้ายแบบคอลัมน์เหลื่อม — report ยังอ่านไฟล์เก่าได้ตามปกติ

## Dashboard สด

เปิด <http://127.0.0.1:8737> — เนื้อหา refresh ผ่าน fetch โดยไม่ reload ทั้งหน้า
เลือกช่วงข้อมูล (1 ชม. – 30 วัน) และ interval (10 วิ – 5 นาที หรือปิด) ได้จาก
มุมขวาบน ค่าที่เลือกกับ theme (🌓) ถูกจำไว้ใน browser และหยุด refresh เอง
เมื่อแท็บถูกซ่อน

## วิธีวัด (สำคัญต่อการตีความข้อมูล)

- **CPU% ไม่ใช่ point sample** — คำนวณจากผลต่างของ cumulative CPU time ของทุก
  process ระหว่าง tick ดังนั้น CPU ที่ถูกใช้ระหว่างสอง sample ถูกนับครบ
  แม้ spike จะสั้นกว่า interval ก็เห็นในค่าเฉลี่ยของช่วงนั้น
- ข้อจำกัด: process ที่เกิดและตายภายใน tick เดียวจะไม่ทิ้งร่องรอย
  (ต้องใช้ process accounting ระดับ root ถึงจะเก็บได้)
- ช่วงเครื่องหลับ = ไม่มีข้อมูล จะเห็นเป็นช่องว่างของ timestamp และ
  กราฟจะตัดเส้นตรงนั้น ไม่ลากเส้นเชื่อมหลอก
- `mem_used_mb` = active + wired + compressor (นิยามเดียวกับ "Memory Used"
  ใน Activity Monitor), RAM ของ process รวมทุก instance ที่ชื่อเดียวกัน

## รายงาน static

```bash
python3 report.py --days 7 && open report.html
```

ได้ไฟล์ HTML ไฟล์เดียวจบ เอาไปเก็บ/แชร์เทียบข้ามช่วงเวลาได้

## จัดการ / ถอนการติดตั้ง

```bash
# ดูสถานะ
launchctl print gui/$(id -u)/local.resmon | head -20
launchctl print gui/$(id -u)/local.resmon.web | head -20

# ถอนการติดตั้ง (เก็บ logs/ ไว้)
./uninstall.sh
```

ถ้าติดตั้งด้วย `RESMON_LABEL` อื่น ให้ตั้งค่าเดียวกันตอนรัน uninstall.sh ด้วย
