# ui.py
import streamlit as st
import pandas as pd
import io
import plotly.graph_objects as go

# Estilos CSS
def load_styles():
    st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        
        .kpi-card {
            background-color: white;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            border: 1px solid #e0e0e0;
            text-align: center;
            color: #444;
            min-height: 110px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .kpi-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #7f8c8d;
            margin-bottom: 8px;
            font-weight: 600;
            min-height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .kpi-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 4px;
        }
        .kpi-note {
            font-size: 0.7rem;
            color: #95a5a6;
        }
        
        /* Colores Semánticos */
        .border-green { border-left: 4px solid #27ae60; }
        .border-orange { border-left: 4px solid #d35400; }
        .border-yellow { border-left: 4px solid #f1c40f; }
        .border-blue { border-left: 4px solid #2980b9; }
        .border-purple { border-left: 4px solid #8e44ad; }
        .border-red { border-left: 4px solid #c0392b; }
        .border-teal { border-left: 4px solid #16a085; }
        .border-cyan { border-left: 4px solid #1abc9c; }
        .border-gray { border-left: 4px solid #7f8c8d; }
        
        /* Fondos de Alerta */
        .bg-dark-blue { background-color: #f0f8ff; border-left: 5px solid #000080; }
        .bg-alert-green { background-color: #e8f8f5; border-left: 5px solid #2ecc71; }
        .bg-alert-warn { background-color: #fef9e7; border-left: 5px solid #f1c40f; }
        .bg-alert-red { background-color: #fdedec; border-left: 5px solid #e74c3c; }
    </style>
    """, unsafe_allow_html=True)

def convert_df_to_excel(df, sheet_name='Datos'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def card_kpi(titulo, valor, color_class, nota="", formato="moneda"):
    try:
        val_float = float(valor)
        es_numero = True
    except:
        es_numero = False
        val_fmt = str(valor)

    if es_numero:
        if formato == "moneda": val_fmt = f"₡ {val_float:,.0f}"
        elif formato == "numero": val_fmt = f"{val_float:,.0f}"
        elif formato == "percent": val_fmt = f"{val_float:.1f}%"
        else: val_fmt = str(valor)
    else:
        val_fmt = str(valor)
        
    st.markdown(f"""
    <div class="kpi-card {color_class}">
        <div class="kpi-title">{titulo}</div>
        <div class="kpi-value">{val_fmt}</div>
        <div class="kpi-note">{nota}</div>
    </div>
    """, unsafe_allow_html=True)

def config_plotly(fig):
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Arial, sans-serif", size=11, color="#333"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.1)
    )
    return fig
