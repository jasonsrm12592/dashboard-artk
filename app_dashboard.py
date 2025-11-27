import streamlit as st
import pandas as pd
import xmlrpc.client
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import io
import os
import ast

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Alrotek Monitor v9.1 (Full)", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilos CSS Profesionales (Cards modernas y limpias)
st.markdown("""
<style>
    /* Ocultar elementos default de Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    
    /* Estilo de Tarjetas KPI */
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

    /* Bordes de color para indicadores */
    .border-green { border-left: 4px solid #27ae60; }
    .border-orange { border-left: 4px solid #d35400; }
    .border-yellow { border-left: 4px solid #f1c40f; }
    .border-blue { border-left: 4px solid #2980b9; }
    .border-purple { border-left: 4px solid #8e44ad; }
    .border-red { border-left: 4px solid #c0392b; }
    .border-teal { border-left: 4px solid #16a085; }
    .border-cyan { border-left: 4px solid #1abc9c; }
    .border-gray { border-left: 4px solid #7f8c8d; }
    .border-light-orange { border-left: 4px solid #f39c12; }

</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES & CONSTANTES ---
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    COMPANY_ID = st.secrets["odoo"]["company_id"]
    
    IDS_INGRESOS = [58, 384]     
    ID_COSTO_RETAIL = 76         
    ID_COSTO_INSTALACION = 399   
    ID_SUMINISTROS_PROY = 400    
    ID_WIP = 503                 
    ID_PROVISION_PROY = 504      
    ID_AJUSTES_INV = 395         
    
    TODOS_LOS_IDS = IDS_INGRESOS + [ID_WIP, ID_PROVISION_PROY, ID_COSTO_INSTALACION, ID_SUMINISTROS_PROY, ID_AJUSTES_INV, ID_COSTO_RETAIL]
    
except Exception:
    st.error("❌ Error Crítico: No se encuentra el archivo .streamlit/secrets.toml con las credenciales.")
    st.stop()

# --- 3. FUNCIONES UTILITARIAS Y UI ---

def convert_df_to_excel(df, sheet_name='Datos'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def card_kpi(titulo, valor, color_class, nota=""):
    if isinstance(valor, str):
        val_fmt = valor
    else:
        val_fmt = f"₡ {valor:,.0f}"
        
    html = f"""
    <div class="kpi-card {color_class}">
        <div class="kpi-title">{titulo}</div>
        <div class="kpi-value">{val_fmt}</div>
        <div class="kpi-note">{nota}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def config_plotly(fig):
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Arial, sans-serif", size=11, color="#333"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig

# --- 4. FUNCIONES DE CARGA DE DATOS (Optimizadas con Cache) ---

@st.cache_data(ttl=900) 
def cargar_datos_generales():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        if not uid: return None
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = [['move_type', 'in', ['out_invoice', 'out_refund']], ['state', '=', 'posted'], ['invoice_date', '>=', '2021-01-01'], ['company_id', '=', COMPANY_ID]]
        campos = ['name', 'invoice_date', 'amount_untaxed_signed', 'partner_id', 'invoice_user_id']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'read', [ids], {'fields': campos})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['Mes'] = df['invoice_date'].dt.to_period('M').dt.to_timestamp()
            df['Mes_Num'] = df['invoice_date'].dt.month
            df['Cliente'] = df['partner_id'].apply(lambda x: x[1] if x else "Sin Cliente")
            df['ID_Cliente'] = df['partner_id'].apply(lambda x: x[0] if x else 0)
            df['Vendedor'] = df['invoice_user_id'].apply(lambda x: x[1] if x else "Sin Asignar")
            df['Venta_Neta'] = df['amount_untaxed_signed']
            df = df[~df['name'].str.contains("WT-", case=False, na=False)]
        return df
    except Exception as e: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_cartera():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = [['move_type', '=', 'out_invoice'], ['state', '=', 'posted'], ['payment_state', 'in', ['not_paid', 'partial']], ['amount_residual', '>', 0], ['company_id', '=', COMPANY_ID]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'read', [ids], {'fields': ['name', 'invoice_date', 'invoice_date_due', 'amount_total', 'amount_residual', 'partner_id', 'invoice_user_id']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['invoice_date_due'] = pd.to_datetime(df['invoice_date_due'])
            df['Cliente'] = df['partner_id'].apply(lambda x: x[1] if x else "Sin Cliente")
            df['Vendedor'] = df['invoice_user_id'].apply(lambda x: x[1] if x else "Sin Asignar")
            df['Dias_Vencido'] = (pd.Timestamp.now() - df['invoice_date_due']).dt.days
            def bucket(d): return "Por Vencer" if d < 0 else ("0-30" if d<=30 else ("31-60" if d<=60 else ("61-90" if d<=90 else "+90")))
            df['Antiguedad'] = df['Dias_Vencido'].apply(bucket)
            df['Antiguedad'] = pd.Categorical(df['Antiguedad'], ["Por Vencer", "0-30", "31-60", "61-90", "+90"], ordered=True)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_datos_clientes_extendido(ids_clientes):
    try:
        if not ids_clientes: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        registros = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'read', [list(ids_clientes)], {'fields': ['state_id', 'x_studio_zona', 'x_studio_categoria_cliente']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Provincia'] = df['state_id'].apply(lambda x: x[1] if x else "Sin Provincia")
            def procesar_campo_studio(valor):
                if isinstance(valor, list): return valor[1]
                if valor: return str(valor)
                return "No Definido"
            df['Zona_Comercial'] = df['x_studio_zona'].apply(procesar_campo_studio) if 'x_studio_zona' in df.columns else "N/A"
            df['Categoria_Cliente'] = df['x_studio_categoria_cliente'].apply(procesar_campo_studio) if 'x_studio_categoria_cliente' in df.columns else "N/A"
            df.rename(columns={'id': 'ID_Cliente'}, inplace=True)
            return df[['ID_Cliente', 'Provincia', 'Zona_Comercial', 'Categoria_Cliente']]
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600) 
def cargar_detalle_productos():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        anio_inicio = datetime.now().year - 1
        dominio = [['parent_state', '=', 'posted'], ['date', '>=', f'{anio_inicio}-01-01'], ['company_id', '=', COMPANY_ID], ['display_type', '=', 'product'], ['move_id.move_type', 'in', ['out_invoice', 'out_refund']]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': ['date', 'product_id', 'credit', 'debit', 'quantity', 'move_id', 'analytic_distribution']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['ID_Factura'] = df['move_id'].apply(lambda x: x[0] if x else 0)
            df['ID_Producto'] = df['product_id'].apply(lambda x: x[0] if x else 0)
            df['Producto'] = df['product_id'].apply(lambda x: x[1] if x else "Otros")
            df['Venta_Neta'] = df['credit'] - df['debit']
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_general():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = [['active', '=', True]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'default_code']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_baja_rotacion():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        try:
            ids_bom_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
            data_boms = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'read', [ids_bom_kits], {'fields': ['product_tmpl_id']})
            ids_tmpl_kits = [b['product_tmpl_id'][0] for b in data_boms if b['product_tmpl_id']]
        except: ids_tmpl_kits = []
        dominio_loc = [['complete_name', 'ilike', 'BP/Stock'], ['usage', '=', 'internal'], ['company_id', '=', COMPANY_ID]]
        ids_locs_raiz = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [dominio_loc])
        if not ids_locs_raiz: return pd.DataFrame(), "❌ No se encontró 'BP/Stock'."
        dominio_quant = [['location_id', 'child_of', ids_locs_raiz], ['quantity', '>', 0], ['company_id', '=', COMPANY_ID]]
        ids_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [dominio_quant])
        data_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [ids_quants], {'fields': ['product_id', 'quantity', 'location_id']})
        df = pd.DataFrame(data_quants)
        if df.empty: return pd.DataFrame(), "Bodega vacía."
        df['pid'] = df['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
        df['Producto'] = df['product_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "Desc.")
        df['Ubicacion'] = df['location_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "-")
        ids_prods_stock = df['pid'].unique().tolist()
        prod_details = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids_prods_stock], {'fields': ['standard_price', 'product_tmpl_id', 'detailed_type']})
        df_prod_info = pd.DataFrame(prod_details)
        df_prod_info['Costo'] = df_prod_info['standard_price']
        df_prod_info['tmpl_id'] = df_prod_info['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
        df = pd.merge(df, df_prod_info[['id', 'Costo', 'tmpl_id', 'detailed_type']], left_on='pid', right_on='id', how='left')
        if ids_tmpl_kits: df = df[~df['tmpl_id'].isin(ids_tmpl_kits)]
        df = df[df['detailed_type'] == 'product']
        df['Valor'] = df['quantity'] * df['Costo']
        if df.empty: return pd.DataFrame(), "Sin productos almacenables."
        fecha_corte = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        ids_prods_final = df['pid'].unique().tolist()
        dominio_moves = [['product_id', 'in', ids_prods_final], ['state', '=', 'done'], ['date', '>=', fecha_corte], ['location_dest_id.usage', 'in', ['customer', 'production']]]
        ids_moves = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'search', [dominio_moves])
        data_moves = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'read', [ids_moves], {'fields': ['product_id', 'date']})
        df_moves = pd.DataFrame(data_moves)
        mapa_ult_salida = {}
        if not df_moves.empty:
            df_moves['pid'] = df_moves['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
            df_moves['date'] = pd.to_datetime(df_moves['date'])
            mapa_ult_salida = df_moves.groupby('pid')['date'].max().to_dict()
        def calc_dias(row):
            pid = row['pid']
            if pid in mapa_ult_salida:
                return (pd.Timestamp.now() - mapa_ult_salida[pid]).days
            else:
                return 366 
        df['Dias_Sin_Salida'] = df.apply(calc_dias, axis=1)
        df_agrupado = df.groupby(['Producto']).agg({'quantity': 'sum', 'Valor': 'sum', 'Dias_Sin_Salida': 'min', 'Ubicacion': lambda x: ", ".join(sorted(set(str(v) for v in x if v)))}).reset_index()
        df_huesos = df_agrupado.sort_values('Dias_Sin_Salida', ascending=False)
        return df_huesos, "OK"
    except Exception as e: return pd.DataFrame(), f"Error: {e}"

@st.cache_data(ttl=3600)
def cargar_estructura_analitica():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_plans = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'search', [[['id', '!=', 0]]])
        plans = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'read', [ids_plans], {'fields': ['name']})
        df_plans = pd.DataFrame(plans).rename(columns={'id': 'plan_id', 'name': 'Plan_Nombre'})
        ids_acc = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'search', [[['active', 'in', [True, False]]]])
        accounts = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'read', [ids_acc], {'fields': ['name', 'plan_id']})
        df_acc = pd.DataFrame(accounts)
        if not df_acc.empty and not df_plans.empty:
            df_acc['plan_id'] = df_acc['plan_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else (x if x else 0))
            df_full = pd.merge(df_acc, df_plans, on='plan_id', how='left')
            df_full.rename(columns={'id': 'id_cuenta_analitica', 'name': 'Cuenta_Nombre'}, inplace=True)
            df_full['Plan_Nombre'] = df_full['Plan_Nombre'].fillna("Sin Plan Asignado")
            return df_full[['id_cuenta_analitica', 'Cuenta_Nombre', 'Plan_Nombre']]
        return pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_pnl_historico():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_gastos = models.execute_kw(DB, uid, PASSWORD, 'account.account', 'search', [[['code', '=like', '6%']]])
        ids_totales = list(set(TODOS_LOS_IDS + ids_gastos))
        dominio_pnl = [['account_id', 'in', ids_totales], ['company_id', '=', COMPANY_ID], ['parent_state', '=', 'posted'], ['analytic_distribution', '!=', False]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio_pnl])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': ['date', 'account_id', 'debit', 'credit', 'analytic_distribution', 'name']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['ID_Cuenta'] = df['account_id'].apply(lambda x: x[0] if x else 0)
            df['Nombre_Cuenta'] = df['account_id'].apply(lambda x: x[1] if x else "Desconocida")
            df['Monto_Neto'] = df['credit'] - df['debit']
            def clasificar(row):
                id_acc = row['ID_Cuenta']
                if id_acc in IDS_INGRESOS: return "Venta"
                if id_acc == ID_WIP: return "WIP"
                if id_acc == ID_PROVISION_PROY: return "Provisión"
                if id_acc == ID_COSTO_INSTALACION: return "Instalación"
                if id_acc == ID_SUMINISTROS_PROY: return "Suministros"
                if id_acc == ID_AJUSTES_INV: return "Ajustes Inv"
                if id_acc == ID_COSTO_RETAIL: return "Costo Retail"
                return "Otros Gastos"
            df['Clasificacion'] = df.apply(clasificar, axis=1)
            def get_analytic_id(dist):
                if not dist: return None
                try: 
                    if isinstance(dist, dict): return int(list(dist.keys())[0])
                except: pass
                return None
            df['id_cuenta_analitica'] = df['analytic_distribution'].apply(get_analytic_id)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_detalle_horas_mes(ids_cuentas_analiticas):
    try:
        if not ids_cuentas_analiticas: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_clean = [int(x) for x in ids_cuentas_analiticas if pd.notna(x) and x != 0]
        if not ids_clean: return pd.DataFrame()
        hoy = datetime.now()
        inicio_mes = hoy.replace(day=1).strftime('%Y-%m-%d')
        dominio = [['account_id', 'in', ids_clean], ['date', '>=', inicio_mes], ['date', '<=', hoy.strftime('%Y-%m-%d')], ['employee_id', '!=', False], ['x_studio_tipo_horas_1', '!=', False]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'read', [ids], {'fields': ['date', 'amount', 'unit_amount', 'x_studio_tipo_horas_1', 'employee_id']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Tipo_Hora'] = df['x_studio_tipo_horas_1'].astype(str)
            df['Multiplicador'] = df['Tipo_Hora'].apply(lambda x: 3.0 if "doble" in x.lower() else (1.5 if "extra" in x.lower() else 1.0))
            df['Costo'] = df['amount'].abs() * df['Multiplicador']
            df['Horas'] = df['unit_amount']
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_inventario_ubicacion_proyecto_v4(ids_cuentas_analiticas, nombres_cuentas_analiticas):
    try:
        if not ids_cuentas_analiticas: return pd.DataFrame(), "SIN_SELECCION", []
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_analytic_clean = [int(x) for x in ids_cuentas_analiticas if pd.notna(x) and x != 0]
        ids_locs_final = []
        if ids_analytic_clean:
            try: ids_locs_final += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', 'in', ids_analytic_clean]]])
            except: pass
        if nombres_cuentas_analiticas:
            for nombre in nombres_cuentas_analiticas:
                if isinstance(nombre, str) and len(nombre) > 4:
                    keyword = nombre.split(' ')[0] 
                    if len(keyword) > 3:
                        ids_locs_final += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['name', 'ilike', keyword]]])
        ids_locs_final = list(set(ids_locs_final))
        if not ids_locs_final: return pd.DataFrame(), "NO_BODEGA", []
        loc_names = [l['complete_name'] for l in models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [ids_locs_final], {'fields': ['complete_name']})]
        ids_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [[['location_id', 'child_of', ids_locs_final], ['company_id', '=', COMPANY_ID]]])
        data_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [ids_quants], {'fields': ['product_id', 'quantity']})
        df = pd.DataFrame(data_quants)
        if df.empty: return pd.DataFrame(), "NO_STOCK", loc_names
        df['pid'] = df['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
        df['pname'] = df['product_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "Desconocido")
        df_grouped = df.groupby(['pid', 'pname']).agg({'quantity': 'sum'}).reset_index()
        ids_prods = df_grouped['pid'].unique().tolist()
        costos = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids_prods], {'fields': ['standard_price']})
        df_costos = pd.DataFrame(costos).rename(columns={'id': 'pid', 'standard_price': 'Costo_Unit'})
        df_final = pd.merge(df_grouped, df_costos, on='pid', how='left')
        df_final['Valor_Total'] = df_final['quantity'] * df_final['Costo_Unit']
        return df_final[df_final['quantity'] != 0], "OK", loc_names
    except Exception as e: return pd.DataFrame(), f"ERR: {str(e)}", []

@st.cache_data(ttl=900)
def cargar_compras_pendientes_v7_json_scanner(ids_cuentas_analiticas, tc_usd):
    try:
        if not ids_cuentas_analiticas: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        targets = [str(int(x)) for x in ids_cuentas_analiticas if pd.notna(x) and x != 0]
        dominio = [['state', 'in', ['purchase', 'done']], ['company_id', '=', COMPANY_ID], ['date_order', '>=', '2023-01-01']]
        ids = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [ids], {'fields': ['order_id', 'partner_id', 'name', 'product_qty', 'qty_invoiced', 'price_unit', 'analytic_distribution', 'currency_id']})
        df = pd.DataFrame(registros)
        if df.empty: return pd.DataFrame()
        def es_mi_proyecto(dist):
            if not dist: return False
            try:
                d = dist if isinstance(dist, dict) else ast.literal_eval(str(dist))
                return any(t in [str(k) for k in d.keys()] for t in targets)
            except: return False
        df['Es_Mio'] = df['analytic_distribution'].apply(es_mi_proyecto)
        df = df[df['Es_Mio']].copy()
        df['qty_pending'] = df['product_qty'] - df['qty_invoiced']
        df = df[df['qty_pending'] > 0]
        if df.empty: return pd.DataFrame()
        def get_monto_local(row):
            monto = row['qty_pending'] * row['price_unit']
            moneda = row['currency_id'][1] if row['currency_id'] else "CRC"
            return monto * tc_usd if moneda == 'USD' else monto
        df['Monto_Pendiente'] = df.apply(get_monto_local, axis=1)
        df['Proveedor'] = df['partner_id'].apply(lambda x: x[1] if x else "-")
        df['OC'] = df['order_id'].apply(lambda x: x[1] if x else "-")
        return df[['OC', 'Proveedor', 'name', 'Monto_Pendiente']]
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_facturacion_estimada_v2(ids_projects, tc_usd):
    try:
        if not ids_projects: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_clean = [int(x) for x in ids_projects if pd.notna(x) and x != 0]
        proyectos_data = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'read', [ids_clean], {'fields': ['name']})
        if not proyectos_data: return pd.DataFrame()
        nombre_buscar = proyectos_data[0]['name']
        dominio = [['x_studio_field_sFPxe', 'ilike', nombre_buscar], ['x_studio_facturado', '=', False]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'read', [ids], {'fields': ['x_name', 'x_Monto', 'x_Fecha']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Monto_CRC'] = df['x_Monto'] * tc_usd
            df['Hito'] = df['x_name'] if 'x_name' in df.columns else "Hito"
            return df
        return pd.DataFrame()
    except: return pd.DataFrame()

def cargar_metas():
    if os.path.exists("metas.xlsx"):
        df = pd.read_excel("metas.xlsx")
        df['Mes'] = pd.to_datetime(df['Mes'])
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})

# --- 5. INTERFAZ PRINCIPAL ---

st.title("🚀 Alrotek Monitor de Ventas")

with st.expander("⚙️ Configuración y Filtros Globales", expanded=True):
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1:
        tc_usd = st.number_input("Tipo de Cambio (USD -> CRC)", value=515, min_value=1, step=1)
    with col_conf2:
        st.info(f"💡 Datos sincronizados con Odoo. TC: ₡{tc_usd}")

tab_kpis, tab_prod, tab_renta, tab_inv, tab_cx, tab_cli, tab_vend, tab_det = st.tabs([
    "📊 Visión General", 
    "📦 Productos", 
    "📈 Proyectos", 
    "🕸️ Baja Rotación", 
    "💰 Cartera",
    "👥 Segmentación",
    "💼 Vendedores",
    "🔍 Radiografía"
])

with st.spinner('Conectando con el nucleo de Odoo...'):
    df_main = cargar_datos_generales()
    df_metas = cargar_metas()
    df_prod = cargar_detalle_productos()
    df_analitica = cargar_estructura_analitica()
    
    if not df_main.empty:
        ids_unicos = df_main['ID_Cliente'].unique().tolist()
        df_info = cargar_datos_clientes_extendido(ids_unicos)
        if not df_info.empty:
            df_main = pd.merge(df_main, df_info, on='ID_Cliente', how='left')
            df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']] = df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']].fillna('Sin Dato')
        else:
            df_main['Provincia'] = 'Sin Dato'

# === PESTAÑA 1: VISIÓN GENERAL (KPIs) ===
with tab_kpis:
    if not df_main.empty:
        anios = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        col_filtro_kpi, _ = st.columns([1,3])
        with col_filtro_kpi:
            anio_sel = st.selectbox("📅 Año Fiscal", anios, key="kpi_anio")
            
        anio_ant = anio_sel - 1
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_sel]
        df_ant_data = df_main[df_main['invoice_date'].dt.year == anio_ant]
        
        venta = df_anio['Venta_Neta'].sum()
        venta_ant_total = df_ant_data['Venta_Neta'].sum()
        delta_anual = ((venta - venta_ant_total) / venta_ant_total * 100) if venta_ant_total > 0 else 0
        metas_filtradas = df_metas[df_metas['Anio'] == anio_sel]
        meta = metas_filtradas['Meta'].sum()
        cant_facturas = df_anio['name'].nunique()
        ticket_promedio = (venta / cant_facturas) if cant_facturas > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: card_kpi("Venta Total", venta, "border-green", f"{delta_anual:+.1f}% vs {anio_ant}")
        with c2: card_kpi("Meta Anual", meta, "border-cyan")
        with c3: card_kpi("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%", "border-blue")
        with c4: card_kpi("Ticket Prom.", ticket_promedio, "border-purple", f"{cant_facturas} Ops")
        
        st.divider()
        col_down, _ = st.columns([1, 4])
        with col_down:
            st.download_button("📥 Descargar Detalle Facturas", 
                             data=convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'Provincia', 'Vendedor', 'Venta_Neta']]), 
                             file_name=f"Ventas_{anio_sel}.xlsx")
                             
        c_graf, c_vend = st.columns([2, 1])
        with c_graf:
            st.subheader("📊 Ventas por Plan Analítico (Restaurado)")
            if not df_prod.empty:
                df_lineas = df_prod[df_prod['date'].dt.year == anio_sel].copy()
                mapa_planes = dict(zip(df_analitica['id_cuenta_analitica'].astype(str), df_analitica['Plan_Nombre'])) if not df_analitica.empty else {}
                def clasificar_plan(dist):
                    if not dist: return "Sin Analítica (Retail)"
                    try:
                        d = dist if isinstance(dist, dict) else ast.literal_eval(str(dist))
                        for k in d.keys():
                            plan = mapa_planes.get(str(k))
                            if plan: return plan
                    except: pass
                    return "Analítica Desconocida"
                df_lineas['Plan_Agrupado'] = df_lineas['analytic_distribution'].apply(clasificar_plan)
                ventas_linea = df_lineas.groupby('Plan_Agrupado')['Venta_Neta'].sum().reset_index()
                fig_pie = px.pie(ventas_linea, values='Venta_Neta', names='Plan_Agrupado', hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
                st.plotly_chart(config_plotly(fig_pie), use_container_width=True)

                st.subheader("📅 Evolución Mensual por Plan")
                df_lineas['Mes_Nombre'] = df_lineas['date'].dt.strftime('%m-%b')
                df_lineas['Mes_Num'] = df_lineas['date'].dt.month
                ventas_mes_plan = df_lineas.groupby(['Mes_Num', 'Mes_Nombre', 'Plan_Agrupado'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                fig_stack = px.bar(ventas_mes_plan, x='Mes_Nombre', y='Venta_Neta', color='Plan_Agrupado', barmode='stack', color_discrete_sequence=px.colors.qualitative.Prism)
                st.plotly_chart(config_plotly(fig_stack), use_container_width=True)

            st.subheader("🎯 Comparativo vs Meta")
            v_mes_act = df_anio.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Actual'})
            v_mes_ant = df_ant_data.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Anterior'})
            v_metas = metas_filtradas.groupby('Mes_Num')['Meta'].sum().reset_index()
            df_chart = pd.DataFrame({'Mes_Num': range(1, 13)})
            df_chart = df_chart.merge(v_mes_ant, on='Mes_Num', how='left').merge(v_mes_act, on='Mes_Num', how='left').merge(v_metas, on='Mes_Num', how='left').fillna(0)
            meses_nombres = {1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic'}
            df_chart['Mes_Nombre'] = df_chart['Mes_Num'].map(meses_nombres)
            colores = ['#2ecc71' if r >= m else '#e74c3c' for r, m in zip(df_chart['Actual'], df_chart['Meta'])]
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(x=df_chart['Mes_Nombre'], y=df_chart['Actual'], name='Real', marker_color=colores))
            fig1.add_trace(go.Scatter(x=df_chart['Mes_Nombre'], y=df_chart['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
            st.plotly_chart(config_plotly(fig1), use_container_width=True)

        with c_vend:
            st.subheader("🏆 Top Vendedores")
            rank_actual = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index().sort_values('Venta_Neta', ascending=True).tail(10)
            fig_v = px.bar(rank_actual, x='Venta_Neta', y='Vendedor', orientation='h', text_auto='.2s')
            st.plotly_chart(config_plotly(fig_v), use_container_width=True)

# === PESTAÑA 2: PRODUCTOS ===
with tab_prod:
    df_cat = cargar_inventario_general()
    if not df_prod.empty and not df_cat.empty:
        col_filtro_p, _ = st.columns([1,3])
        with col_filtro_p:
            anios_p = sorted(df_prod['date'].dt.year.unique(), reverse=True)
            anio_p_sel = st.selectbox("Año Análisis", anios_p, key="prod_anio")
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_p_sel].merge(df_cat[['ID_Producto', 'Tipo', 'Referencia']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]
        
        st.download_button("📥 Descargar Detalle Productos", data=convert_df_to_excel(df_p_anio), file_name=f"Productos_{anio_p_sel}.xlsx")
        
        col_tipo1, col_tipo2 = st.columns([1, 2])
        with col_tipo1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(config_plotly(fig_pie), use_container_width=True)
        with col_tipo2:
            c_f1, c_f2 = st.columns(2)
            with c_f1: tipo_ver = st.radio("Filtrar:", ["Todos", "Almacenable", "Servicio"], horizontal=True)
            with c_f2: metrica_prod = st.radio("Ordenar:", ["Monto (₡)", "Cantidad (Unid.)"], horizontal=True)
            df_show = df_p_anio if tipo_ver == "Todos" else df_p_anio[df_p_anio['Tipo'] == tipo_ver]
            col_orden = 'Venta_Neta' if metrica_prod == "Monto (₡)" else 'quantity'
            top_prod = df_show.groupby('Producto')[[col_orden]].sum().sort_values(col_orden, ascending=False).head(10).sort_values(col_orden, ascending=True)
            fig_bar = px.bar(top_prod, x=col_orden, y=top_prod.index, orientation='h', text_auto='.2s', color=col_orden)
            st.plotly_chart(config_plotly(fig_bar), use_container_width=True)

# === PESTAÑA 3: RENTABILIDAD PROYECTOS (TODO RESTAURADO) ===
with tab_renta:
    df_pnl = cargar_pnl_historico()
    if not df_analitica.empty:
        mapa_cuentas = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Plan_Nombre']))
        mapa_nombres = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Cuenta_Nombre']))
        
        st.markdown("### 🕵️ Buscador de Proyectos")
        c_filt1, c_filt2 = st.columns(2)
        with c_filt1: planes_sel = st.multiselect("Filtrar por Plan:", sorted(list(set(mapa_cuentas.values()))))
        ids_posibles = [id_c for id_c, plan in mapa_cuentas.items() if plan in planes_sel] if planes_sel else []
        nombres_posibles = [mapa_nombres[id_c] for id_c in ids_posibles]
        with c_filt2: cuentas_sel_nombres = st.multiselect("Seleccionar Proyecto:", sorted(nombres_posibles))
            
        if cuentas_sel_nombres:
            ids_seleccionados = [id_c for id_c, nombre in mapa_nombres.items() if nombre in cuentas_sel_nombres]
            try:
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
                uid = common.authenticate(DB, USERNAME, PASSWORD, {})
                models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
                ids_projects = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', ids_seleccionados]]])
            except: ids_projects = []

            df_filtered = df_pnl[df_pnl['id_cuenta_analitica'].isin(ids_seleccionados)].copy() if not df_pnl.empty else pd.DataFrame()
            
            total_ventas = abs(df_filtered[df_filtered['Clasificacion'] == 'Venta']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_instalacion = abs(df_filtered[df_filtered['Clasificacion'] == 'Instalación']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_suministros = abs(df_filtered[df_filtered['Clasificacion'] == 'Suministros']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_wip = abs(df_filtered[df_filtered['Clasificacion'] == 'WIP']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_provision = abs(df_filtered[df_filtered['Clasificacion'] == 'Provisión']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_ajustes = df_filtered[df_filtered['Clasificacion'] == 'Ajustes Inv']['Monto_Neto'].sum() if not df_filtered.empty else 0
            total_costo_retail = abs(df_filtered[df_filtered['Clasificacion'] == 'Costo Retail']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_otros = abs(df_filtered[df_filtered['Clasificacion'] == 'Otros Gastos']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            
            df_horas_detalle = cargar_detalle_horas_mes(ids_seleccionados)
            total_horas = df_horas_detalle['Costo'].sum() if not df_horas_detalle.empty else 0
            df_stock, status_stock, bodegas = cargar_inventario_ubicacion_proyecto_v4(ids_seleccionados, cuentas_sel_nombres)
            total_stock = df_stock['Valor_Total'].sum() if not df_stock.empty else 0
            df_compras = cargar_compras_pendientes_v7_json_scanner(ids_seleccionados, tc_usd)
            total_compras = df_compras['Monto_Pendiente'].sum() if not df_compras.empty else 0
            df_fact = cargar_facturacion_estimada_v2(ids_projects, tc_usd)
            total_fact = df_fact['Monto_CRC'].sum() if not df_fact.empty else 0
            
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Ingresos", total_ventas, "border-green")
            with k2: card_kpi("Costo Instalación", total_instalacion, "border-blue")
            with k3: card_kpi("Costo Suministros", total_suministros, "border-orange")
            with k4: card_kpi("WIP (En Progreso)", total_wip, "border-yellow")
            
            k5, k6, k7, k8 = st.columns(4)
            with k5: card_kpi("Provisiones", total_provision, "border-red")
            with k6: card_kpi("Ajustes Inv.", total_ajustes, "border-gray")
            with k7: card_kpi("Costo Retail", total_costo_retail, "border-orange")
            with k8: card_kpi("Otros Gastos", total_otros, "border-gray")
            
            st.markdown("#### Operativo")
            o1, o2, o3, o4 = st.columns(4)
            with o1: card_kpi("Inv. Sitio", total_stock, "border-purple", f"Bodegas: {len(bodegas)}")
            with o2: card_kpi("Compras Pend.", total_compras, "border-teal")
            with o3: card_kpi("Horas (Mes)", total_horas, "border-blue")
            with o4: card_kpi("Proy. Facturación", total_fact, "border-cyan")
            
            st.divider()
            c_horas, c_stock = st.columns(2)
            with c_horas:
                st.markdown("##### 🕒 Desglose de Horas")
                if not df_horas_detalle.empty:
                    st.dataframe(df_horas_detalle.groupby(['Tipo_Hora', 'Multiplicador'])[['Horas', 'Costo']].sum().reset_index(), use_container_width=True)
                else: st.info("Sin horas este mes.")
            with c_stock:
                st.markdown("##### 📦 Detalle Materiales")
                t1, t2, t3 = st.tabs(["Inventario", "Compras", "Fact. Pend."])
                with t1: st.dataframe(df_stock, use_container_width=True)
                with t2: st.dataframe(df_compras, use_container_width=True)
                with t3: st.dataframe(df_fact, use_container_width=True)
            
            st.markdown("##### Detalle Movimientos Contables")
            if not df_filtered.empty:
                st.dataframe(df_filtered[['date', 'name', 'Nombre_Cuenta', 'Clasificacion', 'Monto_Neto']].sort_values(['Clasificacion', 'date']), use_container_width=True)

# === PESTAÑA 4: BAJA ROTACIÓN ===
with tab_inv:
    if st.button("🔄 Calcular Rotación (Puede tardar)"):
        with st.spinner("Analizando..."):
            df_huesos, msg_status = cargar_inventario_baja_rotacion()
        if not df_huesos.empty:
            dias_min = st.slider("Días sin Salidas:", 0, 720, 365)
            df_show = df_huesos[df_huesos['Dias_Sin_Salida'] >= dias_min]
            col_res1, col_res2, col_res3 = st.columns(3)
            with col_res1: card_kpi("Capital Estancado", df_show['Valor'].sum(), "border-red")
            with col_res2: card_kpi("Total Items", len(df_huesos), "border-gray")
            with col_res3: card_kpi("Items Críticos", len(df_show), "border-orange")
            st.dataframe(df_show[['Producto', 'Ubicacion', 'quantity', 'Dias_Sin_Salida', 'Valor']], use_container_width=True)
        else: st.info(msg_status)

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    df_cx = cargar_cartera()
    if not df_cx.empty:
        total_deuda = df_cx['amount_residual'].sum()
        total_vencido = df_cx[df_cx['Dias_Vencido'] > 0]['amount_residual'].sum()
        pct_vencido = (total_vencido / total_deuda * 100) if total_deuda > 0 else 0
        
        cx1, cx2, cx3 = st.columns(3)
        with cx1: card_kpi("Total por Cobrar", total_deuda, "border-blue")
        with cx2: card_kpi("Vencido (>1 día)", total_vencido, "border-red")
        with cx3: card_kpi("Salud Cartera", f"{100-pct_vencido:.1f}% Al Día", "border-green")
        
        col_cx_g1, col_cx_g2 = st.columns([2, 1])
        with col_cx_g1:
            df_buckets = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            colores_cx = {"Por Vencer": "#2ecc71", "0-30": "#f1c40f", "31-60": "#e67e22", "61-90": "#e74c3c", "+90": "#c0392b"}
            fig_cx = px.bar(df_buckets, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad', color_discrete_map=colores_cx)
            st.plotly_chart(config_plotly(fig_cx), use_container_width=True)
        with col_cx_g2:
            st.markdown("#### Top Deudores")
            st.dataframe(df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).head(10), use_container_width=True)
        
        st.download_button("📥 Descargar Reporte Cobros", data=convert_df_to_excel(df_cx[['invoice_date', 'name', 'Cliente', 'amount_residual', 'Antiguedad']]), file_name="Cartera.xlsx")

# === PESTAÑA 6: SEGMENTACIÓN (TODO RESTAURADO) ===
with tab_cli:
    if not df_main.empty:
        anio_c_sel = st.selectbox("Año Análisis", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        
        c_map1, c_map2, c_map3 = st.columns(3)
        with c_map1:
            st.markdown("##### Por Provincia")
            st.plotly_chart(config_plotly(px.pie(df_c_anio.groupby('Provincia')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Provincia', hole=0.4)), use_container_width=True)
        with c_map2:
            st.markdown("##### Por Zona")
            st.plotly_chart(config_plotly(px.pie(df_c_anio.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Zona_Comercial', hole=0.4)), use_container_width=True)
        with c_map3:
            st.markdown("##### Por Categoría")
            st.plotly_chart(config_plotly(px.pie(df_c_anio.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Categoria_Cliente', hole=0.4)), use_container_width=True)
        
        st.divider()
        df_c_ant = df_main[df_main['invoice_date'].dt.year == (anio_c_sel - 1)]
        cli_antes = set(df_c_ant[df_c_ant['Venta_Neta'] > 0]['Cliente'])
        cli_ahora = set(df_c_anio[df_c_anio['Venta_Neta'] > 0]['Cliente'])
        lista_perdidos = list(cli_antes - cli_ahora)
        lista_nuevos = list(cli_ahora - cli_antes)
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: card_kpi("Clientes Activos", len(cli_ahora), "border-blue")
        with k2: card_kpi("Clientes Nuevos", len(lista_nuevos), "border-green")
        with k3: card_kpi("Perdidos (Churn)", len(lista_perdidos), "border-red")
        with k4: card_kpi("Tasa Retención", f"{len(cli_antes.intersection(cli_ahora))/len(cli_antes)*100:.1f}%" if cli_antes else "100%", "border-purple")
        
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1: st.download_button("📂 Ranking Completo", data=convert_df_to_excel(df_c_anio.groupby('Cliente')['Venta_Neta'].sum().reset_index()), file_name=f"Ranking_{anio_c_sel}.xlsx")
        with col_d2: 
            if lista_nuevos: st.download_button("🌱 Lista Nuevos", data=convert_df_to_excel(df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]), file_name="Nuevos.xlsx")
        with col_d3:
            if lista_perdidos: st.download_button("📉 Lista Perdidos", data=convert_df_to_excel(df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]), file_name="Perdidos.xlsx")
        
        c_top, c_loss = st.columns(2)
        with c_top:
            st.subheader("Top 10 Clientes")
            top_10 = df_c_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
            st.plotly_chart(config_plotly(px.bar(top_10, x='Venta_Neta', y=top_10.index, orientation='h', text_auto='.2s')), use_container_width=True)
        with c_loss:
            st.subheader("Top Perdidos (Oportunidad)")
            if lista_perdidos:
                df_lost = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                st.plotly_chart(config_plotly(px.bar(df_lost, x='Venta_Neta', y=df_lost.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 7: VENDEDORES (TODO RESTAURADO) ===
with tab_vend:
    if not df_main.empty:
        col_v1, col_v2 = st.columns(2)
        with col_v1: anio_v_sel = st.selectbox("Año", anios, key="vend_anio")
        with col_v2: vendedor_sel = st.selectbox("Vendedor", sorted(df_main['Vendedor'].unique()))
        
        df_v_anio = df_main[(df_main['invoice_date'].dt.year == anio_v_sel) & (df_main['Vendedor'] == vendedor_sel)]
        df_v_ant = df_main[(df_main['invoice_date'].dt.year == (anio_v_sel - 1)) & (df_main['Vendedor'] == vendedor_sel)]
        
        cli_v_antes = set(df_v_ant[df_v_ant['Venta_Neta'] > 0]['Cliente'])
        cli_v_ahora = set(df_v_anio[df_v_anio['Venta_Neta'] > 0]['Cliente'])
        perdidos_v = list(cli_v_antes - cli_v_ahora)
        
        kv1, kv2, kv3 = st.columns(3)
        with kv1: card_kpi("Venta Total", df_v_anio['Venta_Neta'].sum(), "border-green")
        with kv2: card_kpi("Clientes Activos", df_v_anio['Cliente'].nunique(), "border-blue")
        with kv3: card_kpi("Clientes en Riesgo", len(perdidos_v), "border-red")
        
        col_dv1, col_dv2 = st.columns(2)
        with col_dv1: st.download_button(f"📥 Ventas {vendedor_sel}", data=convert_df_to_excel(df_v_anio), file_name=f"Ventas_{vendedor_sel}.xlsx")
        with col_dv2: 
            if perdidos_v: st.download_button("📞 Lista Recuperación", data=convert_df_to_excel(df_v_ant[df_v_ant['Cliente'].isin(perdidos_v)]), file_name=f"Recuperar_{vendedor_sel}.xlsx")

        c_v_top, c_v_lost = st.columns(2)
        with c_v_top:
            st.subheader("Mejores Clientes")
            top_cli_v = df_v_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
            st.plotly_chart(config_plotly(px.bar(top_cli_v, x=top_cli_v.values, y=top_cli_v.index, orientation='h', text_auto='.2s')), use_container_width=True)
        with c_v_lost:
            st.subheader("Cartera Perdida")
            if perdidos_v:
                df_lost_v = df_v_ant[df_v_ant['Cliente'].isin(perdidos_v)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                st.plotly_chart(config_plotly(px.bar(df_lost_v, x='Venta_Neta', y=df_lost_v.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 8: RADIOGRAFÍA (TODO RESTAURADO) ===
with tab_det:
    if not df_main.empty:
        cli_sel = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()))
        if cli_sel:
            df_cli = df_main[df_main['Cliente'] == cli_sel]
            ultima = df_cli['invoice_date'].max()
            dias_sin = (datetime.now() - ultima).days
            prov = df_cli.iloc[0]['Provincia'] if 'Provincia' in df_cli.columns else "N/A"
            
            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1: card_kpi("Total Histórico", df_cli['Venta_Neta'].sum(), "border-green")
            with kc2: card_kpi("Última Compra", ultima.strftime('%d-%m-%Y'), "border-blue")
            with kc3: card_kpi("Días sin Comprar", dias_sin, "border-red" if dias_sin > 90 else "border-gray")
            with kc4: card_kpi("Ubicación", prov, "border-purple")
            
            c_hist, c_prod = st.columns(2)
            with c_hist:
                st.subheader("Historial Anual")
                hist = df_cli.groupby(df_cli['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                st.plotly_chart(config_plotly(px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s')), use_container_width=True)
            with c_prod:
                st.subheader("Top Productos")
                metrica_cli = st.radio("Ver:", ["Monto", "Cantidad"], horizontal=True, label_visibility="collapsed")
                if not df_prod.empty:
                    ids_facturas = set(df_cli['id'])
                    df_prod_cli = df_prod[df_prod['ID_Factura'].isin(ids_facturas)]
                    col_orden = 'Venta_Neta' if metrica_cli == "Monto" else 'quantity'
                    top_p = df_prod_cli.groupby('Producto')[[col_orden]].sum().sort_values(col_orden, ascending=False).head(10)
                    st.plotly_chart(config_plotly(px.bar(top_p, x=col_orden, y=top_p.index, orientation='h', text_auto='.2s')), use_container_width=True)
                    st.download_button("📥 Descargar Historial", data=convert_df_to_excel(df_prod_cli), file_name=f"Historial_{cli_sel}.xlsx")
