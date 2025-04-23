import pyodbc
import pandas as pd
import os
from dotenv import load_dotenv, find_dotenv
from sqlalchemy.engine import URL, create_engine

# Load environment variables
load_dotenv(find_dotenv())

# Read credentials from .env
server = os.getenv("DB_SERVER")
database = os.getenv("DB_DATABASE")
username = os.getenv("DB_USERNAME")
password = os.getenv("DB_PASSWORD")

# Connection string
conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'

# SQLAlchemy connection URL
connection_url = URL.create("mssql+pyodbc", query={"odbc_connect": conn_str})
db_engine = create_engine(connection_url)


def execute_query_df(sql_in):
    with db_engine.begin() as conn:
        df = pd.read_sql(sql_in, conn)
        pd.set_option('display.max_columns', None)
        print(f'Dataframe \n\n {df}')
    return df
