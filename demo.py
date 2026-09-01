from awpy import Demo
dem = Demo ("spirit-vs-vitality-m3-dust2.dem")
dem.parse()
print (dem.kills)
ticks_df = dem.ticks.to_pandas()
print(ticks_df.head())