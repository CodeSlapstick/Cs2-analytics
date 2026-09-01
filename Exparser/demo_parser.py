from pathlib import Path
import pandas as pd
from awpy import Demo

DEMO_FILE = "demos/faze-vs-spirit-m1-dust2.dem"   # ไฟล์ .dem อยู่ใน demos/
OUTPUT_EXCEL = "output/cs2_parsed_data.xlsx"

def to_pandas_df(df_obj) -> pd.DataFrame:
    """แปลง dataframe ไม่ว่าจะเป็น Polars หรือ Pandas ให้เป็น Pandas เสมอ"""
    if df_obj is None:
        return pd.DataFrame()
    if hasattr(df_obj, "to_pandas"):
        return df_obj.to_pandas()
    if isinstance(df_obj, pd.DataFrame):
        return df_obj.copy()
    return pd.DataFrame(df_obj)

def parse_demo_to_excel(demo_path: str, output_path: str):
    path = Path(demo_path)
    if not path.exists():
        print(f"Error: ไม่พบไฟล์ {demo_path} ในโฟลเดอร์")
        return

    print(f"กำลังเริ่มประมวลผลไฟล์: {demo_path} ...")
    print("ขั้นตอนนี้อาจใช้เวลาประมาณ 30-60 วินาที ขึ้นอยู่กับขนาดของเดโม...")
    
    dem = Demo(str(path))
    dem.parse()

    # ดึงและแปลงเป็น Pandas DataFrame
    rounds_df = to_pandas_df(dem.rounds)
    kills_df = to_pandas_df(dem.kills)

    # สกัด First Kill / First Death ต่อรอบ
    if not kills_df.empty and "round_num" in kills_df.columns and "tick" in kills_df.columns:
        kills_df = kills_df.sort_values(["round_num", "tick"])
        first_event_idx = kills_df.groupby("round_num")["tick"].idxmin()
        kills_df["is_first_kill"] = False
        kills_df["is_first_death"] = False
        kills_df.loc[first_event_idx, ["is_first_kill", "is_first_death"]] = True

    print("กำลังสร้างไฟล์ Excel...")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        rounds_df.to_excel(writer, sheet_name="Rounds_Data", index=False)
        kills_df.to_excel(writer, sheet_name="Kill_Coordinates", index=False)

    print(f" แปลงไฟล์สำเร็จเรียบร้อย! ได้ไฟล์: {output_path}")

if __name__ == "__main__":
    parse_demo_to_excel(DEMO_FILE, OUTPUT_EXCEL)