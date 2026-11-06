import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import plotly.express as px

API_URL = os.environ.get('API_URL', 'http://api:8000')
API_USERNAME = os.environ.get('API_USERNAME', 'admin')
API_PASSWORD = os.environ.get('API_PASSWORD', 'admin123')

st.set_page_config(page_title='ИТ-инфраструктура — Дашборд', layout='wide')
st.title('📊 ИИ-агент: анализ данных микросервисов')
st.caption(f'Источник данных: {API_URL} (через VPN-туннель к API на server-b)')

def get_token():
    resp = requests.post(
        f'{API_URL}/login',
        json={'username': API_USERNAME, 'password': API_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['access_token']

@st.cache_data(ttl=30)
def load_data():
    token = get_token()
    resp = requests.get(
        f'{API_URL}/events/export',
        headers={'Authorization': f'Bearer {token}'},
        timeout=30,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['is_error'] = df['status_code'] >= 400
    return df

col_a, col_b = st.columns([1, 5])
with col_a:
    if st.button('🔄 Обновить данные'):
        st.cache_data.clear()

try:
    df = load_data()
except Exception as e:
    st.error(f'Не удалось получить данные с API: {e}')
    st.stop()

if df.empty:
    st.warning('В базе пока нет данных. Вызовите POST /seed на API.')
    st.stop()

# --- KPI ---
total = len(df)
error_rate = df['is_error'].mean() * 100
avg_latency = df['response_time_ms'].mean()
p95_latency = df['response_time_ms'].quantile(0.95)

k1, k2, k3, k4 = st.columns(4)
k1.metric('Всего запросов', f'{total:,}')
k2.metric('Доля ошибок (4xx/5xx)', f'{error_rate:.1f}%')
k3.metric('Средняя задержка', f'{avg_latency:.0f} мс')
k4.metric('P95 задержка', f'{p95_latency:.0f} мс')

st.divider()

# --- Почасовая агрегация ---
hourly = df.groupby('hour').agg(
    requests=('id', 'count'),
    avg_latency=('response_time_ms', 'mean'),
    error_rate=('is_error', 'mean'),
).reset_index()
hourly['error_rate'] = hourly['error_rate'] * 100

c1, c2 = st.columns(2)
with c1:
    st.subheader('Нагрузка по часам')
    fig1 = px.bar(hourly, x='hour', y='requests', labels={'hour': 'Час', 'requests': 'Кол-во запросов'})
    st.plotly_chart(fig1, use_container_width=True)
with c2:
    st.subheader('Средняя задержка по часам')
    fig2 = px.line(hourly, x='hour', y='avg_latency', markers=True, labels={'hour': 'Час', 'avg_latency': 'Задержка, мс'})
    st.plotly_chart(fig2, use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.subheader('Запросы по сервисам')
    by_service = df['service_name'].value_counts().reset_index()
    by_service.columns = ['service_name', 'count']
    fig3 = px.pie(by_service, names='service_name', values='count')
    st.plotly_chart(fig3, use_container_width=True)
with c4:
    st.subheader('Коды ответа')
    by_status = df['status_code'].value_counts().reset_index()
    by_status.columns = ['status_code', 'count']
    fig4 = px.bar(by_status, x='status_code', y='count')
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# --- Простая AI-справка (rule-based анализ аномалий) ---
st.subheader('🤖 Автоматическая справка по статусу')

overall_avg = hourly['avg_latency'].mean()
overall_std = hourly['avg_latency'].std()
threshold = overall_avg + 1.5 * overall_std

insights = []
for _, row in hourly.iterrows():
    if row['avg_latency'] > threshold:
        insights.append(
            f"⚠️ Замечен аномальный рост задержки в {int(row['hour']):02d}:00 "
            f"(средняя задержка {row['avg_latency']:.0f} мс против общего среднего {overall_avg:.0f} мс), "
            f"доля ошибок в этот час: {row['error_rate']:.1f}%."
        )

if insights:
    for line in insights:
        st.warning(line)
else:
    st.success('Аномалий по задержке не обнаружено — все часы в пределах нормы.')

st.caption(f'Отчёт сформирован: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
