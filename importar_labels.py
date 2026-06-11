import os
import pandas as pd
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

print("DATABASE_URL =", DATABASE_URL)

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não configurada.")

engine = create_engine(DATABASE_URL)

PESQUISA_ID = int(os.getenv("PESQUISA_ID"))
XLSFORM = os.getenv("XLSFORM")

df = pd.read_excel(XLSFORM, sheet_name="survey")

df = df[["type", "name", "label"]].dropna(subset=["name", "label"])
df = df[~df["type"].astype(str).str.startswith(("begin", "end", "note"), na=False)]

with engine.begin() as conn:
    conn.execute(text("""
        DELETE FROM perguntas_pesquisa
        WHERE pesquisa_id = :pesquisa_id
    """), {"pesquisa_id": PESQUISA_ID})

    for ordem, row in df.iterrows():
        conn.execute(text("""
            INSERT INTO perguntas_pesquisa (pesquisa_id, name, label, type, ordem)
            VALUES (:pesquisa_id, :name, :label, :type, :ordem)
        """), {
            "pesquisa_id": PESQUISA_ID,
            "name": str(row["name"]).strip(),
            "label": str(row["label"]).strip(),
            "type": str(row["type"]).strip(),
            "ordem": int(ordem)
        })

print("Labels importados com sucesso.")
