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
    page_title="Alrotek Monitor v9.0", 
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
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    
    /* Estilo de Tarjetas KPI */
    .kpi-card {
        background-color: white;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #f0f0f0;
        transition: transform 0.2s;
        text-align: center;
        color: #444;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.1);
    }
    
    .kpi-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #888;
        margin-bottom: 8px;
        font-weight: 600;
        height: 35px; /* Altura fija para alineación */
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .kpi-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #2c3e50;
        margin-bottom: 5px;
    }
    
    .kpi-note {
        font-size: 0.75rem;
        color: #95a5a6;
        font-style: italic;
    }

    /* Indicadores de color laterales en las tarjetas (Barra izquierda) */
    .border-green { border-left: 5px solid #27ae60; }
    .border-orange { border-left: 5px solid #d35400; }
    .border-yellow { border-left: 5px solid #f1c40f; }
    .border-blue { border-left: 5px solid #2980b9; }
    .border-purple { border-left: 5px solid #8e44ad; }
    .border-red { border-left: 5px solid #c0392b; }
    .border-teal { border-left: 5px solid #16a085; }
    .border-cyan { border-left: 5px solid #1abc9c; }
    .border-gray { border-left: 5px solid #7f8c8d; }
    .border-light-orange { border-left: 5px solid #f39c12; }

</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES & CONSTANTES (Mantenemos tus IDs fijos) ---
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
    """
    Componente visual de tarjeta KPI modernizada.
    color_class espera: 'border-green', 'border-red', etc.
    """
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
    """Aplica configuración estándar profesional a los gráficos."""
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=20, r=20, t=40, b=20),
        font=dict(family="Arial, sans-serif", size=12, color="#333"),
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
        
        # Filtro optimizado
        dominio = [['move_type', 'in', ['out_invoice', 'out_refund']], 
                   ['state', '=', 'posted'], 
                   ['invoice_date', '>=', '2021-01-01'], 
                   ['company_id', '=', COMPANY_ID]]
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
            # Excluir retenciones si aplica
            df = df[~df['name'].str.contains("WT-", case=False, na=False)]
        return df
    except Exception as e: 
        print(f"Error General: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_cartera():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = [['move_type', '=', 'out_invoice'], ['state', '=', 'posted'], 
                   ['payment_state', 'in', ['not_paid', 'partial']], 
                   ['amount_residual', '>', 0], ['company_id', '=', COMPANY_ID]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'read', [ids], 
                                    {'fields': ['name', 'invoice_date', 'invoice_date_due', 'amount_total', 'amount_residual', 'partner_id', 'invoice_user_id']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['invoice_date_due'] = pd.to_datetime(df['invoice_date_due'])
            df['Cliente'] = df['partner_id'].apply(lambda x: x[1] if x else "Sin Cliente")
            df['Vendedor'] = df['invoice_user_id'].apply(lambda x: x[1] if x else "Sin Asignar")
            df['Dias_Vencido'] = (pd.Timestamp.now() - df['invoice_date_due']).dt.days
            
            def bucket(d): 
                if d < 0: return "Por Vencer"
                if d <= 30: return "0-30"
                if d <= 60: return "31-60"
                if d <= 90: return "61-90"
                return "+90"
                
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
        registros = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'read', [list(ids_clientes)], 
                                    {'fields': ['state_id', 'x_studio_zona', 'x_studio_categoria_cliente']})
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
        dominio = [['parent_state', '=', 'posted'], ['date', '>=', f'{anio_inicio}-01-01'], 
                   ['company_id', '=', COMPANY_ID], ['display_type', '=', 'product'], 
                   ['move_id.move_type', 'in', ['out_invoice', 'out_refund']]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], 
                                    {'fields': ['date', 'product_id', 'credit', 'debit', 'quantity', 'move_id', 'analytic_distribution']})
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
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], 
                                    {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'default_code']})
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
    # ... (Misma lógica compleja de tu código original, mantenida intacta) ...
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
        
        dominio_pnl = [['account_id', 'in', ids_totales], ['company_id', '=', COMPANY_ID], 
                       ['parent_state', '=', 'posted'], ['analytic_distribution', '!=', False]]
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
            # Buscar por campo Studio
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
        registros = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [ids], 
                                    {'fields': ['order_id', 'partner_id', 'name', 'product_qty', 'qty_invoiced', 'price_unit', 'analytic_distribution', 'currency_id']})
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

# ZONA DE FILTROS SUPERIOR (Reemplazo de Sidebar)
with st.expander("⚙️ Configuración y Filtros Globales", expanded=True):
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1:
        tc_usd = st.number_input("Tipo de Cambio (USD -> CRC)", value=515, min_value=1, step=1)
    with col_conf2:
        st.info(f"💡 Datos sincronizados con Odoo. TC: ₡{tc_usd}")

# CONTENEDOR DE PESTAÑAS
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

# CARGA INICIAL DE DATOS BASE
with st.spinner('Conectando con el nucleo de Odoo...'):
    df_main = cargar_datos_generales()
    df_metas = cargar_metas()
    
    if not df_main.empty:
        # Enriquecer datos de clientes
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
        # Filtros locales
        anios = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        col_filtro_kpi, _ = st.columns([1,3])
        with col_filtro_kpi:
            anio_sel = st.selectbox("📅 Año Fiscal", anios, key="kpi_anio")
            
        anio_ant = anio_sel - 1
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_sel]
        df_ant_data = df_main[df_main['invoice_date'].dt.year == anio_ant]
        
        # Cálculos
        venta = df_anio['Venta_Neta'].sum()
        venta_ant_total = df_ant_data['Venta_Neta'].sum()
        delta_anual = ((venta - venta_ant_total) / venta_ant_total * 100) if venta_ant_total > 0 else 0
        
        metas_filtradas = df_metas[df_metas['Anio'] == anio_sel]
        meta = metas_filtradas['Meta'].sum()
        
        cant_facturas = df_anio['name'].nunique()
        ticket_promedio = (venta / cant_facturas) if cant_facturas > 0 else 0
        
        # UI KPIs
        c1, c2, c3, c4 = st.columns(4)
        with c1: card_kpi("Venta Total", venta, "border-green", f"{delta_anual:+.1f}% vs {anio_ant}")
        with c2: card_kpi("Meta Anual", meta, "border-cyan")
        with c3: card_kpi("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%", "border-blue")
        with c4: card_kpi("Ticket Prom.", ticket_promedio, "border-purple", f"{cant_facturas} Ops")
        
        st.divider()
        
        # Gráficos
        c_graf, c_vend = st.columns([2, 1])
        
        with c_graf:
            st.subheader("📊 Comparativo vs Meta")
            
            # Preparar datos gráfico
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
            
            # Botón Exportar
            st.download_button("📥 Descargar Detalle Facturas", 
                             data=convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'Provincia', 'Vendedor', 'Venta_Neta']]), 
                             file_name=f"Ventas_{anio_sel}.xlsx")

        with c_vend:
            st.subheader("🏆 Top Vendedores")
            rank_actual = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index()
            rank_actual = rank_actual.sort_values('Venta_Neta', ascending=True).tail(10)
            
            fig_v = px.bar(rank_actual, x='Venta_Neta', y='Vendedor', orientation='h', text_auto='.2s', color_discrete_sequence=['#3498db'])
            fig_v.update_layout(yaxis_title=None, xaxis_title=None)
            st.plotly_chart(config_plotly(fig_v), use_container_width=True)

# === PESTAÑA 2: PRODUCTOS ===
with tab_prod:
    # Carga bajo demanda
    df_prod = cargar_detalle_productos()
    df_cat = cargar_inventario_general()
    
    if not df_prod.empty and not df_cat.empty:
        col_filtro_p, _ = st.columns([1,3])
        with col_filtro_p:
            anios_p = sorted(df_prod['date'].dt.year.unique(), reverse=True)
            anio_p_sel = st.selectbox("Año Análisis", anios_p, key="prod_anio")
            
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_p_sel].merge(df_cat[['ID_Producto', 'Tipo', 'Referencia']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]
        
        col_tipo1, col_tipo2 = st.columns([1, 2])
        with col_tipo1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_layout(showlegend=False, annotations=[dict(text='Mix', x=0.5, y=0.5, font_size=20, showarrow=False)])
            st.plotly_chart(config_plotly(fig_pie), use_container_width=True)
            
        with col_tipo2:
            st.markdown("#### Top 10 Productos")
            top_prod = df_p_anio.groupby('Producto')['Venta_Neta'].sum().nlargest(10).sort_values(ascending=True).reset_index()
            fig_bar = px.bar(top_prod, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s', color='Venta_Neta', color_continuous_scale='Bluyl')
            st.plotly_chart(config_plotly(fig_bar), use_container_width=True)
            
        st.download_button("📥 Descargar Detalle Productos", data=convert_df_to_excel(df_p_anio), file_name=f"Productos_{anio_p_sel}.xlsx")

# === PESTAÑA 3: RENTABILIDAD PROYECTOS ===
with tab_renta:
    df_pnl = cargar_pnl_historico()
    df_analitica = cargar_estructura_analitica()
    
    if not df_analitica.empty:
        mapa_cuentas = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Plan_Nombre']))
        mapa_nombres = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Cuenta_Nombre']))
        
        st.markdown("### 🕵️ Buscador de Proyectos")
        c_filt1, c_filt2 = st.columns(2)
        with c_filt1:
            planes_sel = st.multiselect("Filtrar por Plan:", sorted(list(set(mapa_cuentas.values()))))
        
        ids_posibles = [id_c for id_c, plan in mapa_cuentas.items() if plan in planes_sel] if planes_sel else []
        nombres_posibles = [mapa_nombres[id_c] for id_c in ids_posibles]
        
        with c_filt2:
            cuentas_sel_nombres = st.multiselect("Seleccionar Proyecto:", sorted(nombres_posibles))
            
        if cuentas_sel_nombres:
            ids_seleccionados = [id_c for id_c, nombre in mapa_nombres.items() if nombre in cuentas_sel_nombres]
            
            # Buscar IDs Projects relacionados
            try:
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
                uid = common.authenticate(DB, USERNAME, PASSWORD, {})
                models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
                ids_projects = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', ids_seleccionados]]])
            except: ids_projects = []

            # Filtrar Data
            df_filtered = df_pnl[df_pnl['id_cuenta_analitica'].isin(ids_seleccionados)].copy() if not df_pnl.empty else pd.DataFrame()
            
            # KPIs Financieros
            total_ventas = abs(df_filtered[df_filtered['Clasificacion'] == 'Venta']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_instalacion = abs(df_filtered[df_filtered['Clasificacion'] == 'Instalación']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_suministros = abs(df_filtered[df_filtered['Clasificacion'] == 'Suministros']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            total_wip = abs(df_filtered[df_filtered['Clasificacion'] == 'WIP']['Monto_Neto'].sum()) if not df_filtered.empty else 0
            
            # Operativos
            df_stock, status_stock, bodegas = cargar_inventario_ubicacion_proyecto_v4(ids_seleccionados, cuentas_sel_nombres)
            total_stock = df_stock['Valor_Total'].sum() if not df_stock.empty else 0
            
            df_compras = cargar_compras_pendientes_v7_json_scanner(ids_seleccionados, tc_usd)
            total_compras = df_compras['Monto_Pendiente'].sum() if not df_compras.empty else 0
            
            df_fact = cargar_facturacion_estimada_v2(ids_projects, tc_usd)
            total_fact = df_fact['Monto_CRC'].sum() if not df_fact.empty else 0
            
            # Visualización KPIs
            st.markdown("#### Estado Financiero")
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Ingresos", total_ventas, "border-green")
            with k2: card_kpi("Costo Instalación", total_instalacion, "border-blue")
            with k3: card_kpi("Costo Suministros", total_suministros, "border-orange")
            with k4: card_kpi("WIP (En Progreso)", total_wip, "border-yellow")
            
            st.markdown("#### Estado Operativo")
            o1, o2, o3 = st.columns(3)
            with o1: card_kpi("Inventario Sitio", total_stock, "border-purple", f"Bodegas: {len(bodegas)}")
            with o2: card_kpi("Compras Pendientes", total_compras, "border-teal")
            with o3: card_kpi("Fact. Proyectada", total_fact, "border-cyan")
            
            with st.expander("Ver Detalle Inventario y Compras"):
                t1, t2 = st.tabs(["Inventario", "Compras"])
                with t1: st.dataframe(df_stock if not df_stock.empty else pd.DataFrame(), use_container_width=True)
                with t2: st.dataframe(df_compras if not df_compras.empty else pd.DataFrame(), use_container_width=True)

# === PESTAÑA 4: BAJA ROTACIÓN ===
with tab_inv:
    if st.button("🔄 Calcular Rotación (Esto puede tardar unos segundos)"):
        with st.spinner("Analizando movimientos de bodega..."):
            df_huesos, msg_status = cargar_inventario_baja_rotacion()
        
        if not df_huesos.empty:
            dias_min = st.slider("Días sin Salidas:", 0, 720, 365)
            df_show = df_huesos[df_huesos['Dias_Sin_Salida'] >= dias_min]
            
            col_res1, col_res2 = st.columns(2)
            with col_res1: card_kpi("Capital Estancado", df_show['Valor'].sum(), "border-red")
            with col_res2: card_kpi("Items Críticos", len(df_show), "border-orange")
            
            st.dataframe(
                df_show[['Producto', 'Ubicacion', 'quantity', 'Dias_Sin_Salida', 'Valor']],
                column_config={"Valor": st.column_config.NumberColumn(format="₡ %.2f"), "Dias_Sin_Salida": st.column_config.ProgressColumn("Días Inactivo", min_value=0, max_value=720)},
                use_container_width=True
            )
        else:
            st.info(msg_status)

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    df_cx = cargar_cartera()
    if not df_cx.empty:
        total_deuda = df_cx['amount_residual'].sum()
        total_vencido = df_cx[df_cx['Dias_Vencido'] > 0]['amount_residual'].sum()
        
        cx1, cx2 = st.columns(2)
        with cx1: card_kpi("Total por Cobrar", total_deuda, "border-blue")
        with cx2: card_kpi("Vencido (>1 día)", total_vencido, "border-red")
        
        col_cx_g1, col_cx_g2 = st.columns([2, 1])
        with col_cx_g1:
            df_buckets = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            colores_cx = {"Por Vencer": "#2ecc71", "0-30": "#f1c40f", "31-60": "#e67e22", "61-90": "#e74c3c", "+90": "#c0392b"}
            fig_cx = px.bar(df_buckets, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad', color_discrete_map=colores_cx)
            st.plotly_chart(config_plotly(fig_cx), use_container_width=True)
            
        with col_cx_g2:
            st.markdown("#### Top Deudores")
            st.dataframe(df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).head(10), use_container_width=True)

# === PESTAÑA 6: SEGMENTACIÓN ===
with tab_cli:
    if not df_main.empty:
        anio_c_sel = st.selectbox("Año Análisis", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        
        c_map1, c_map2 = st.columns(2)
        with c_map1:
            st.subheader("Por Provincia")
            fig_prov = px.pie(df_c_anio.groupby('Provincia')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Provincia', hole=0.4)
            st.plotly_chart(config_plotly(fig_prov), use_container_width=True)
        with c_map2:
            st.subheader("Por Categoría")
            fig_cat = px.pie(df_c_anio.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Categoria_Cliente', hole=0.4)
            st.plotly_chart(config_plotly(fig_cat), use_container_width=True)

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        col_v1, col_v2 = st.columns(2)
        with col_v1: anio_v_sel = st.selectbox("Año", anios, key="vend_anio")
        with col_v2: vendedor_sel = st.selectbox("Vendedor", sorted(df_main['Vendedor'].unique()))
        
        df_v = df_main[(df_main['invoice_date'].dt.year == anio_v_sel) & (df_main['Vendedor'] == vendedor_sel)]
        
        if not df_v.empty:
            kv1, kv2 = st.columns(2)
            with kv1: card_kpi("Venta Total", df_v['Venta_Neta'].sum(), "border-green")
            with kv2: card_kpi("Clientes Activos", df_v['Cliente'].nunique(), "border-blue")
            
            st.markdown("#### Top Clientes")
            top_cli = df_v.groupby('Cliente')['Venta_Neta'].sum().nlargest(10).sort_values(ascending=True)
            fig_vt = px.bar(top_cli, x=top_cli.values, y=top_cli.index, orientation='h', text_auto='.2s')
            st.plotly_chart(config_plotly(fig_vt), use_container_width=True)
        else:
            st.warning("No hay ventas para este vendedor en el año seleccionado.")

# === PESTAÑA 8: RADIOGRAFÍA (DETAIL) ===
with tab_det:
    if not df_main.empty:
        cli_sel = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()))
        if cli_sel:
            df_cli = df_main[df_main['Cliente'] == cli_sel]
            
            c_det1, c_det2 = st.columns(2)
            with c_det1:
                st.subheader("Historial de Compras")
                hist = df_cli.groupby(df_cli['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                fig_h = px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s')
                st.plotly_chart(config_plotly(fig_h), use_container_width=True)
                
            with c_det2:
                card_kpi("Total Histórico", df_cli['Venta_Neta'].sum(), "border-green")
                card_kpi("Última Compra", df_cli['invoice_date'].max().strftime('%d-%m-%Y'), "border-gray")
