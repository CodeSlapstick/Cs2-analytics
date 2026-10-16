#!/bin/bash
MODE=$1
CONTAINER=$(docker ps -qf "name=postgres")

if [ "$MODE" = "10" ]; then
    echo "⚡ ปรับ Match 55 Round 3 เป็น: กู้แบบไม่มีคีม (10 วินาที)"
    docker exec -i $CONTAINER psql -U postgres -d cs2_analytics -c "
    UPDATE rounds 
    SET defuse_intervals = '[{\"end_tick\": 65971, \"steam_id\": \"76561198064058958\", \"start_tick\": 65331, \"has_kit\": false}]'::json 
    WHERE match_id = 55 AND round_num = 3;
    "
elif [ "$MODE" = "5" ]; then
    echo "⚡ ปรับ Match 55 Round 3 เป็น: กู้แบบมีคีม (5 วินาที)"
    docker exec -i $CONTAINER psql -U postgres -d cs2_analytics -c "
    UPDATE rounds 
    SET defuse_intervals = '[{\"end_tick\": 65651, \"steam_id\": \"76561198064058958\", \"start_tick\": 65331, \"has_kit\": true}]'::json 
    WHERE match_id = 55 AND round_num = 3;
    "
else
    echo "วิธีใช้: ./toggle_defuse.sh 5 (มีคีม) หรือ ./toggle_defuse.sh 10 (ไม่มีคีม)"
fi
