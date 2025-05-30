# import google.generativeai as genai
# import pandas as pd
# import json
# from dotenv import load_dotenv, find_dotenv
# load_dotenv(find_dotenv())

# def explain_result(sql_prompt, sql_result):
#     user_prompt = f"""Summarize the results from the SQL query in less than or up to four sentences. 
#     The result is an output from the following query: {sql_prompt}.
#     Result: {sql_result}. 
#     In the response, do not mention database-related words like SQL, rows, timestamps, etc."""

#     models = genai.GenerativeModel('gemini-2.0-flash')
#     response = models.generate_content(user_prompt)
#     explanation = response.text
    
#     result_summary = explanation
#     result_list = None

#     if "list" in sql_prompt.lower():
#         result_list = sql_result.to_json(orient='records')
        
#     # print(explanation)
#     return result_summary, result_list  



