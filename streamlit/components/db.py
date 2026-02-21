import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


@st.cache_resource
def get_engine():
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "oura")
    user = os.environ.get("POSTGRES_USER", "oura")
    pw = os.environ.get("POSTGRES_PASSWORD", "oura")
    url = URL.create(
        "postgresql",
        username=user, password=pw,
        host=host, port=int(port), database=db,
    )
    return create_engine(url, pool_pre_ping=True)


def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})
