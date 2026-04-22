# ui.py v1.0.2 (Forced Reload)
import streamlit as st
import pandas as pd
import io
import plotly.graph_objects as go

# Estilos CSS
def load_styles():
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet" />
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        
        /* Controles Minimalistas */
        div[data-testid="stMultiSelect"] label p { font-size: 0.85rem !important; color: #7f8c8d !important; font-weight: 500;}
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] { font-size: 0.85rem !important; }
        
        @keyframes fadeUpIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .kpi-card {
            background-color: white;
            border-radius: 40px;
            padding: 10px 20px 10px 12px;
            margin-bottom: 15px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.04);
            border: 2px solid #eaeaef;
            display: flex;
            flex-direction: row;
            align-items: center;
            min-height: 80px;
            animation: fadeUpIn 0.6s cubic-bezier(0.16, 1, 0.3, 1);
            transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.1);
        }
        .kpi-icon-box {
            font-size: 1.8rem;
            margin-right: 15px;
            width: 45px;
            height: 45px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            background-color: #f8f9fa;
            transition: transform 0.3s ease;
        }
        .kpi-card:hover .kpi-icon-box {
            transform: scale(1.15) rotate(-5deg);
            background-color: #f0f2f5;
        }
        .kpi-info {
            display: flex;
            flex-direction: column;
            justify-content: center;
            flex: 1;
        }
        .kpi-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #7f8c8d;
            margin-bottom: 2px;
            font-weight: 600;
        }
        .kpi-value {
            font-size: 1.25rem;
            color: #2c3e50;
            margin-bottom: 1px;
            font-weight: 700;
            line-height: 1.1;
        }
        .kpi-note {
            font-size: 0.65rem;
            color: #95a5a6;
            line-height: 1.1;
        }
        
        /* Colores Semánticos */
        .border-green { border-color: #27ae60 !important; }
        .border-orange { border-color: #d35400 !important; }
        .border-yellow { border-color: #f1c40f !important; }
        .border-blue { border-color: #2980b9 !important; }
        .border-purple { border-color: #8e44ad !important; }
        .border-red { border-color: #c0392b !important; }
        .border-teal { border-color: #16a085 !important; }
        .border-cyan { border-color: #1abc9c !important; }
        .border-gray { border-color: #7f8c8d !important; }
        
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

def download_button(df, filename, label="📥 Descargar Excel"):
    """Genera un botón de descarga para un DataFrame en formato Excel."""
    if df is not None and not df.empty:
        buffer = convert_df_to_excel(df)
        st.download_button(
            label=label,
            data=buffer,
            file_name=f"{filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def get_icon_for_title(title):
    t = title.lower()
    if 'ingreso' in t or 'venta' in t or 'facturado' in t or 'cobrar' in t: return "payments"
    if 'costo' in t or 'gasto' in t or 'compras' in t or 'pendientes' in t: return "trending_down"
    if 'margen' in t or 'utilidad' in t or 'salud' in t: return "trending_up"
    if 'inventario' in t or 'stock' in t or 'suministros' in t: return "inventory_2"
    if 'horas' in t or 'tiempo' in t or 'instalación' in t: return "schedule"
    if 'wip' in t or 'proceso' in t or 'ajustes' in t: return "build"
    if 'cliente' in t or 'vendedor' in t or 'retención' in t: return "group"
    if 'meta' in t or 'cumplimiento' in t: return "track_changes"
    if 'ticket' in t or 'provisión' in t: return "receipt_long"
    if 'alerta' in t or 'riesgo' in t or 'vencido' in t or 'churn' in t or 'capital' in t: return "warning"
    return "analytics"

def card_kpi(titulo, valor, color_class, nota="", formato="moneda", icono=None):
    if not icono:
        icono = get_icon_for_title(titulo)
        
    try:
        val_float = float(valor)
        es_numero = True
    except:
        es_numero = False
        val_fmt = str(valor)

    if es_numero:
        if formato == "moneda": val_fmt = f"₡ {val_float:,.0f}"
        elif formato == "usd": val_fmt = f"$ {val_float:,.0f}"
        elif formato == "numero": val_fmt = f"{val_float:,.0f}"
        elif formato == "percent": val_fmt = f"{val_float:.1f}%"
        else: val_fmt = str(valor)
    else:
        val_fmt = str(valor)
        
    st.markdown(f"""
    <div class="kpi-card {color_class}">
        <div class="kpi-icon-box">
            <span class="material-symbols-outlined" style="font-size: 26px; color: #7f8c8d;">{icono}</span>
        </div>
        <div class="kpi-info">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{val_fmt}</div>
            <div class="kpi-note">{nota}</div>
        </div>
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
