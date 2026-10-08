#!/system/bin/sh
# 8790: รับ HTTP แล้วตอบ ok (ทดสอบ self-IP)
# 8791: รับ HTTP แล้วเขียนข้อมูลที่ได้ลงไฟล์ + ตอบ ok
RESP="HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
while true; do
  printf "$RESP" | toybox nc -l -p 8790 -q 1
done &
while true; do
  BODY=$(printf "$RESP" | toybox nc -l -p 8791 -q 1 | tee -a /storage/emulated/0/Delta/Workspace/nc_8791_recv.txt)
done &
wait
