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
    page_title="Alrotek Monitor v1", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilos CSS
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

# --- 2. CREDENCIALES ---
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
    st.error("❌ Error: Credenciales no encontradas en .streamlit/secrets.toml")
    st.stop()

# --- 3. FUNCIONES UTILITARIAS ---
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

# --- 4. CARGA DE DATOS ---
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
            df = df.drop(columns=['partner_id', 'invoice_user_id'], errors='ignore')
            df['Venta_Neta'] = df['amount_untaxed_signed']
            df = df[~df['name'].str.contains("WT-", case=False, na=False)]
        return df
    except: return pd.DataFrame()

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
            df = df.drop(columns=['partner_id', 'invoice_user_id'], errors='ignore')
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
            def procesar_campo_studio(valor): return str(valor[1]) if isinstance(valor, list) else (str(valor) if valor else "No Definido")
            df['Zona_Comercial'] = df['x_studio_zona'].apply(procesar_campo_studio) if 'x_studio_zona' in df.columns else "N/A"
            df['Categoria_Cliente'] = df['x_studio_categoria_cliente'].apply(procesar_campo_studio) if 'x_studio_categoria_cliente' in df.columns else "N/A"
            df = df.drop(columns=['state_id', 'x_studio_zona', 'x_studio_categoria_cliente'], errors='ignore')
            df.rename(columns={'id': 'ID_Cliente'}, inplace=True)
            return df[['ID_Cliente', 'Provincia', 'Zona_Comercial', 'Categoria_Cliente']]
        return pd.DataFrame()
    except: return pd.DataFrame()

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
            df = df.drop(columns=['product_id', 'move_id'], errors='ignore')
            df['Venta_Neta'] = df['credit'] - df['debit']
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_general():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = ['|', ['active', '=', True], ['active', '=', False]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'default_code']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_baja_rotacion():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        try: ids_tmpl_kits = [b['product_tmpl_id'][0] for b in models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'read', [models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])], {'fields': ['product_tmpl_id']}) if b['product_tmpl_id']]
        except: ids_tmpl_kits = []
        ids_locs = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['complete_name', 'ilike', 'BP/Stock'], ['usage', '=', 'internal'], ['company_id', '=', COMPANY_ID]]])
        if not ids_locs: return pd.DataFrame(), "❌ No BP/Stock"
        data_q = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [[['location_id', 'child_of', ids_locs], ['quantity', '>', 0], ['company_id', '=', COMPANY_ID]]])], {'fields': ['product_id', 'quantity', 'location_id']})
        df = pd.DataFrame(data_q)
        if df.empty: return pd.DataFrame(), "Bodega vacía"
        df['pid'] = df['product_id'].apply(lambda x: x[0] if isinstance(x,list) else x)
        df['Producto'] = df['product_id'].apply(lambda x: x[1] if isinstance(x,list) else "-")
        df['Ubicacion'] = df['location_id'].apply(lambda x: x[1] if isinstance(x,list) else "-")
        df = df.drop(columns=['product_id', 'location_id'], errors='ignore')
        info = pd.DataFrame(models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [df['pid'].unique().tolist()], {'fields': ['standard_price', 'product_tmpl_id', 'detailed_type']}))
        info['Costo'] = info['standard_price']
        info['tmpl_id'] = info['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
        df = pd.merge(df, info, left_on='pid', right_on='id', how='left')
        if ids_tmpl_kits: df = df[~df['tmpl_id'].isin(ids_tmpl_kits)]
        df = df[df['detailed_type'] == 'product']
        df['Valor'] = df['quantity'] * df['Costo']
        moves = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'read', [models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'search', [[['product_id', 'in', df['pid'].unique().tolist()], ['state', '=', 'done'], ['date', '>=', (datetime.now()-timedelta(days=365)).strftime('%Y-%m-%d')], ['location_dest_id.usage', 'in', ['customer', 'production']]]])], {'fields': ['product_id', 'date']})
        mapa = pd.DataFrame(moves)
        mapa_dict = {}
        if not mapa.empty:
            mapa['pid'] = mapa['product_id'].apply(lambda x: x[0])
            mapa['date'] = pd.to_datetime(mapa['date'])
            mapa_dict = mapa.groupby('pid')['date'].max().to_dict()
        df['Dias_Sin_Salida'] = df['pid'].apply(lambda x: (pd.Timestamp.now()-mapa_dict[x]).days if x in mapa_dict else 366)
        res = df.groupby('Producto').agg({'quantity':'sum', 'Valor':'sum', 'Dias_Sin_Salida':'min', 'Ubicacion': lambda x: ", ".join(sorted(set(str(v) for v in x)))}).reset_index().sort_values('Dias_Sin_Salida', ascending=False)
        return res, "OK"
    except Exception as e: return pd.DataFrame(), f"Err: {e}"

@st.cache_data(ttl=3600)
def cargar_estructura_analitica():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        plans = pd.DataFrame(models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'read', [models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'search', [[['id', '!=', 0]]])], {'fields': ['name']})).rename(columns={'id': 'plan_id', 'name': 'Plan_Nombre'})
        accs = pd.DataFrame(models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'read', [models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'search', [[['active', 'in', [True, False]]]])], {'fields': ['name', 'plan_id']}))
        if not accs.empty:
            accs['plan_id'] = accs['plan_id'].apply(lambda x: x[0] if isinstance(x,list) else (x if x else 0))
            df = pd.merge(accs, plans, on='plan_id', how='left').rename(columns={'id': 'id_cuenta_analitica', 'name': 'Cuenta_Nombre'})
            df['Plan_Nombre'] = df['Plan_Nombre'].fillna("Sin Plan")
            return df[['id_cuenta_analitica', 'Cuenta_Nombre', 'Plan_Nombre']]
        return pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_pnl_historico():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids = list(set(TODOS_LOS_IDS + models.execute_kw(DB, uid, PASSWORD, 'account.account', 'search', [[['code', '=like', '6%']]])))
        data = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [[['account_id', 'in', ids], ['company_id', '=', COMPANY_ID], ['parent_state', '=', 'posted'], ['analytic_distribution', '!=', False]]])], {'fields': ['date', 'account_id', 'debit', 'credit', 'analytic_distribution']})
        df = pd.DataFrame(data)
        if not df.empty:
            df['ID_Cuenta'] = df['account_id'].apply(lambda x: x[0])
            def get_aid(d):
                try: return int(list((d if isinstance(d,dict) else ast.literal_eval(str(d))).keys())[0])
                except: return None
            df['id_cuenta_analitica'] = df['analytic_distribution'].apply(get_aid)
            df = df.drop(columns=['account_id', 'analytic_distribution'], errors='ignore')
            df['Monto_Neto'] = df['credit'] - df['debit']
            def clasificar(id_acc):
                if id_acc in IDS_INGRESOS: return "Venta"
                if id_acc == ID_WIP: return "WIP"
                if id_acc == ID_PROVISION_PROY: return "Provisión"
                if id_acc == ID_COSTO_INSTALACION: return "Instalación"
                if id_acc == ID_SUMINISTROS_PROY: return "Suministros"
                if id_acc == ID_AJUSTES_INV: return "Ajustes Inv"
                if id_acc == ID_COSTO_RETAIL: return "Costo Retail"
                return "Otros Gastos"
            df['Clasificacion'] = df['ID_Cuenta'].apply(clasificar)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_detalle_horas_mes(ids):
    try:
        if not ids: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        hoy = datetime.now()
        ids_l = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'search', [[['account_id', 'in', [int(x) for x in ids if x]], ['date', '>=', hoy.replace(day=1).strftime('%Y-%m-%d')], ['date', '<=', hoy.strftime('%Y-%m-%d')], ['x_studio_tipo_horas_1', '!=', False]]])
        data = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'read', [ids_l], {'fields': ['amount', 'unit_amount', 'x_studio_tipo_horas_1']})
        df = pd.DataFrame(data)
        if not df.empty:
            df['Multiplicador'] = df['x_studio_tipo_horas_1'].astype(str).apply(lambda x: 3.0 if "doble" in x.lower() else (1.5 if "extra" in x.lower() else 1.0))
            df['Costo'] = df['amount'].abs() * df['Multiplicador']
            df['Horas'] = df['unit_amount']
            df['Tipo_Hora'] = df['x_studio_tipo_horas_1']
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_inventario_ubicacion_proyecto_v4(ids_an, names_an):
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_loc = []
        if ids_an: 
            try: ids_loc += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', 'in', [int(x) for x in ids_an if x]]]])
            except: pass
        if names_an:
            for n in names_an:
                if len(n)>4: ids_loc += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['name', 'ilike', n.split(' ')[0]]]])
        ids_loc = list(set(ids_loc))
        if not ids_loc: return pd.DataFrame(), "NO_BODEGA", []
        names = [l['complete_name'] for l in models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [ids_loc], {'fields': ['complete_name']})]
        data = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [[['location_id', 'child_of', ids_loc], ['company_id', '=', COMPANY_ID]]])], {'fields': ['product_id', 'quantity']})
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(), "NO_STOCK", names
        df['pid'] = df['product_id'].apply(lambda x: x[0])
        df['pname'] = df['product_id'].apply(lambda x: x[1])
        grp = df.groupby(['pid', 'pname'])['quantity'].sum().reset_index()
        costos = pd.DataFrame(models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [grp['pid'].unique().tolist()], {'fields': ['standard_price']})).rename(columns={'id':'pid', 'standard_price':'Costo'})
        fin = pd.merge(grp, costos, on='pid', how='left')
        fin['Valor_Total'] = fin['quantity'] * fin['Costo']
        return fin[fin['quantity']!=0], "OK", names
    except Exception as e: return pd.DataFrame(), str(e), []

@st.cache_data(ttl=900)
def cargar_compras_pendientes_v7_json_scanner(ids_an, tc):
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        targets = [str(int(x)) for x in ids_an if x]
        data = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'search', [[['state', 'in', ['purchase', 'done']], ['company_id', '=', COMPANY_ID], ['date_order', '>=', '2023-01-01']]])], {'fields': ['order_id', 'partner_id', 'name', 'product_qty', 'qty_invoiced', 'price_unit', 'analytic_distribution', 'currency_id']})
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame()
        def es_mio(d):
            try: return any(t in [str(k) for k in (d if isinstance(d,dict) else ast.literal_eval(str(d))).keys()] for t in targets)
            except: return False
        df = df[df['analytic_distribution'].apply(es_mio)].copy()
        df['qty_pending'] = df['product_qty'] - df['qty_invoiced']
        df = df[df['qty_pending'] > 0]
        if df.empty: return pd.DataFrame()
        df['Monto_Pendiente'] = df.apply(lambda r: (r['qty_pending']*r['price_unit']) * (tc if r['currency_id'] and r['currency_id'][1]=='USD' else 1), axis=1)
        df['Proveedor'] = df['partner_id'].apply(lambda x: x[1])
        df['OC'] = df['order_id'].apply(lambda x: x[1])
        df = df.drop(columns=['order_id', 'partner_id', 'analytic_distribution', 'currency_id'], errors='ignore')
        return df[['OC', 'Proveedor', 'name', 'Monto_Pendiente']]
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_facturacion_estimada_v2(ids_analiticas, tc_usd):
    try:
        if not ids_analiticas: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_clean_an = [int(x) for x in ids_analiticas if pd.notna(x) and x != 0]
        ids_proys = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', ids_clean_an]]])
        if not ids_proys: return pd.DataFrame()
        proyectos_data = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'read', [ids_proys], {'fields': ['name']})
        if not proyectos_data: return pd.DataFrame()
        nombres_buscar = [p['name'] for p in proyectos_data if p['name']]
        if not nombres_buscar: return pd.DataFrame()
        nombre_buscar = nombres_buscar[0] 
        dominio = [['x_studio_field_sFPxe', 'ilike', nombre_buscar], ['x_studio_facturado', '=', False]]
        ids_fact = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'search', [dominio])
        if not ids_fact: return pd.DataFrame()
        registros = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'read', [ids_fact], {'fields': ['x_name', 'x_Monto', 'x_Fecha']})
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

# --- 5. INTERFAZ ---
st.image("logo.png", width=100)
st.title("Alrotek Monitor v1")

with st.expander("⚙️ Configuración", expanded=True):
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1: tc_usd = st.number_input("TC (USD -> CRC)", value=515)
    with col_conf2: st.info(f"TC: ₡{tc_usd}")

tab_kpis, tab_renta, tab_prod, tab_inv, tab_cx, tab_cli, tab_vend, tab_det = st.tabs(["📊 Visión General", "📈 Rentabilidad Proyectos", "📦 Productos", "🕸️ Baja Rotación", "💰 Cartera", "👥 Segmentación", "💼 Vendedores", "🔍 Radiografía"])

with st.spinner('Cargando...'):
    df_main = cargar_datos_generales()
    df_metas = cargar_metas()
    df_prod = cargar_detalle_productos()
    df_an = cargar_estructura_analitica()
    
    if not df_main.empty:
        df_info = cargar_datos_clientes_extendido(df_main['ID_Cliente'].unique().tolist())
        if not df_info.empty:
            df_main = pd.merge(df_main, df_info, on='ID_Cliente', how='left')
            df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']] = df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']].fillna('Sin Dato')
        else:
            # FIX: Inicializar columnas vacías si falla la carga extendida
            df_main['Provincia'] = 'Sin Dato'
            df_main['Zona_Comercial'] = 'Sin Dato'
            df_main['Categoria_Cliente'] = 'Sin Dato'

# === PESTAÑA 1: VISIÓN GENERAL ===
with tab_kpis:
    if not df_main.empty:
        col_f, _ = st.columns([1,3])
        with col_f: anio_sel = st.selectbox("📅 Año Fiscal", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True))
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_sel]
        df_ant = df_main[df_main['invoice_date'].dt.year == (anio_sel - 1)]
        
        venta = df_anio['Venta_Neta'].sum()
        delta = ((venta - df_ant['Venta_Neta'].sum()) / df_ant['Venta_Neta'].sum() * 100) if df_ant['Venta_Neta'].sum() > 0 else 0
        meta = df_metas[df_metas['Anio'] == anio_sel]['Meta'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: card_kpi("Venta Total", venta, "border-green", f"{delta:+.1f}% vs Anterior")
        with c2: card_kpi("Meta Anual", meta, "bg-dark-blue", formato="moneda")
        with c3: card_kpi("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%", "border-blue", formato="raw")
        with c4: card_kpi("Ticket Prom.", (venta/df_anio['name'].nunique()) if df_anio['name'].nunique()>0 else 0, "border-purple")
        
        st.divider()
        st.download_button("📥 Descargar", data=convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'amount_untaxed_signed']]), file_name=f"Ventas_{anio_sel}.xlsx")

        st.markdown(f"### 🎯 Cumplimiento de Meta ({anio_sel})")
        v_act = df_anio.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Actual'})
        v_meta = df_metas[df_metas['Anio'] == anio_sel].groupby('Mes_Num')['Meta'].sum().reset_index()
        df_gm = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_meta, on='Mes_Num', how='left').fillna(0)
        df_gm['Mes'] = df_gm['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=df_gm['Mes'], y=df_gm['Actual'], name='Actual', marker_color=['#2ecc71' if r>=m else '#e74c3c' for r,m in zip(df_gm['Actual'], df_gm['Meta'])]))
        fig_m.add_trace(go.Scatter(x=df_gm['Mes'], y=df_gm['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
        st.plotly_chart(config_plotly(fig_m), use_container_width=True)

        st.divider()
        st.markdown(f"### 🗓️ Comparativo: {anio_sel} vs {anio_sel-1}")
        v_ant_g = df_ant.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Anterior'})
        df_gc = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_ant_g, on='Mes_Num', how='left').fillna(0)
        df_gc['Mes'] = df_gc['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Actual'], name=f'{anio_sel}', marker_color='#2980b9'))
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Anterior'], name=f'{anio_sel-1}', marker_color='#95a5a6'))
        st.plotly_chart(config_plotly(fig_c), use_container_width=True)

# --- NUEVO: GRÁFICO VENTAS SEMANA ACTUAL ---
        st.divider()
        st.markdown("### 📅 Ventas Semana Actual")
        
        hoy = datetime.now()
        # Calcular lunes (0) y domingo (6) de la semana actual
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        
        # Filtrar datos de la semana actual
        mask_semana = (df_main['invoice_date'].dt.date >= inicio_semana.date()) & \
                      (df_main['invoice_date'].dt.date <= fin_semana.date())
        df_semana = df_main[mask_semana].copy()
        
        if not df_semana.empty:
            # Mapeo manual para asegurar nombres en español
            df_semana['Dia_Num'] = df_semana['invoice_date'].dt.weekday
            mapa_dias = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
            df_semana['Dia_Nom'] = df_semana['Dia_Num'].map(mapa_dias)
            
            # Agrupar y ordenar
            v_semana = df_semana.groupby(['Dia_Num', 'Dia_Nom'])['Venta_Neta'].sum().reset_index().sort_values('Dia_Num')
            
            # Crear gráfico
            fig_w = px.bar(v_semana, x='Dia_Nom', y='Venta_Neta', text_auto='.2s', 
                           title=f"Semana del {inicio_semana.strftime('%d/%m')} al {fin_semana.strftime('%d/%m')}")
            fig_w.update_traces(marker_color='#1abc9c') # Color cian para diferenciar
            st.plotly_chart(config_plotly(fig_w), use_container_width=True)
        else:
            st.info(f"💤 No hay ventas registradas aún en la semana del {inicio_semana.strftime('%d/%m')}.")
        
        st.divider()
        c_mix, c_top = st.columns(2)
        with c_mix:
            st.subheader("📊 Mix por Plan")
            if not df_prod.empty:
                df_l = df_prod[df_prod['date'].dt.year == anio_sel].copy()
                mapa = dict(zip(df_an['id_cuenta_analitica'].astype(str), df_an['Plan_Nombre'])) if not df_an.empty else {}
                def clasif(d):
                    if not d: return "Retail"
                    try: return mapa.get(str(list((d if isinstance(d,dict) else ast.literal_eval(str(d))).keys())[0]), "Otro")
                    except: return "Otro"
                df_l['Plan'] = df_l['analytic_distribution'].apply(clasif)
                
                df_l['Mes_Num'] = df_l['date'].dt.month
                df_l['Mes_Nom'] = df_l['date'].dt.strftime('%m-%b')
                
                df_grp = df_l.groupby(['Mes_Num', 'Mes_Nom', 'Plan'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                
                # --- NUEVO: Cálculo de % por mes ---
                # 1. Calcular el total vendido por mes para usarlo de base (100%)
                df_grp['Total_Mes'] = df_grp.groupby('Mes_Num')['Venta_Neta'].transform('sum')
                
                # 2. Calcular el porcentaje formateado (ej. 25.4%)
                df_grp['Pct_Texto'] = df_grp.apply(lambda x: f"{x['Venta_Neta']/x['Total_Mes']:.1%}" if x['Total_Mes'] != 0 else "0%", axis=1)
                
                # 3. Crear gráfico incluyendo el texto
                fig_mix = px.bar(df_grp, x='Mes_Nom', y='Venta_Neta', color='Plan', 
                                 text='Pct_Texto',  # Aquí asignamos el porcentaje como texto
                                 title="")
                
                # 4. Ajustar para que el texto se vea bien dentro de la barra
                fig_mix.update_traces(textposition='inside', textfont_size=10)
                
                st.plotly_chart(config_plotly(fig_mix), use_container_width=True)
       
        with c_top:
            st.subheader("🏆 Top Vendedores")
            r_act = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index()
            r_ant = df_ant.groupby('Vendedor')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta':'Venta_Ant'})
            r_fin = pd.merge(r_act, r_ant, on='Vendedor', how='left').fillna(0)
            
            def txt(row):
                d = ((row['Venta_Neta'] - row['Venta_Ant'])/row['Venta_Ant']*100) if row['Venta_Ant']>0 else 100
                i = "⬆️" if d>=0 else "⬇️"
                return f"₡{row['Venta_Neta']/1e6:.1f}M {i} {d:.0f}%"
            
            r_fin['T'] = r_fin.apply(txt, axis=1)
            st.plotly_chart(config_plotly(go.Figure(go.Bar(x=r_fin.sort_values('Venta_Neta').tail(10)['Venta_Neta'], y=r_fin.sort_values('Venta_Neta').tail(10)['Vendedor'], orientation='h', text=r_fin.sort_values('Venta_Neta').tail(10)['T'], textposition='auto', marker_color='#2ecc71'))), use_container_width=True)

# === PESTAÑA 2: PROYECTOS (ESTRUCTURA v10.7) ===
with tab_renta:
    df_pnl = cargar_pnl_historico()
    if not df_an.empty:
        c1, c2 = st.columns(2)
        mapa_c = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Plan_Nombre']))
        mapa_n = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Cuenta_Nombre']))
        
        with c1: planes = st.multiselect("Planes:", sorted(list(set(mapa_c.values()))))
        posibles = [id for id, p in mapa_c.items() if p in planes] if planes else []
        nombres = [mapa_n[id] for id in posibles]
        with c2: proys = st.multiselect("Proyectos:", sorted(nombres))
        
        if proys:
            sel_ids = [id for id, n in mapa_n.items() if n in proys]
            df_f = df_pnl[df_pnl['id_cuenta_analitica'].isin(sel_ids)] if not df_pnl.empty else pd.DataFrame()
            totales = {k: abs(df_f[df_f['Clasificacion']==k]['Monto_Neto'].sum()) if not df_f.empty else 0 
                      for k in ['Venta','Instalación','Suministros','WIP','Provisión','Costo Retail','Otros Gastos']}
            totales['Ajustes Inv'] = df_f[df_f['Clasificacion']=='Ajustes Inv']['Monto_Neto'].sum() if not df_f.empty else 0
            
            # Cargas Operativas
            df_h = cargar_detalle_horas_mes(sel_ids)
            df_s, _, bods = cargar_inventario_ubicacion_proyecto_v4(sel_ids, proys)
            df_c = cargar_compras_pendientes_v7_json_scanner(sel_ids, tc_usd)
            df_fe = cargar_facturacion_estimada_v2(sel_ids, tc_usd)
            
            # CALCULOS FINALES v10.7 (ALERTA OPERATIVA)
            # 1. Ingresos (Total Proyecto)
            total_fact = totales['Venta']
            total_pend = df_fe['Monto_CRC'].sum() if not df_fe.empty else 0
            total_ing = total_fact + total_pend
            
            # 2. Costo Operativo (TRANSITORIO - SOLO ALERTA)
            costo_vivo = (
                (df_s['Valor_Total'].sum() if not df_s.empty else 0) + # Inventario
                totales['WIP'] + # WIP
                (df_c['Monto_Pendiente'].sum() if not df_c.empty else 0) + # Compras Pend
                (df_h['Costo'].sum() if not df_h.empty else 0) # Horas
            )
            
            # 3. Margen Alerta (Ingreso Total - Costo Vivo)
            margen_alerta = total_ing - costo_vivo
            pct_alerta = (margen_alerta / total_ing * 100) if total_ing > 0 else 0
            
            color_alerta = "bg-alert-green" if pct_alerta > 30 else ("bg-alert-warn" if pct_alerta > 10 else "bg-alert-red")

            st.markdown("#### 🚦 Semáforo de Alerta Operativa")
            st.caption("Margen calculado como: (Total Ingresos - Costos Vivos). Excluye costos contables cerrados y provisiones.")
            
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Ingreso Total Proy.", total_ing, "border-green")
            with k2: card_kpi("Costo Vivo (Alerta)", costo_vivo, "border-red")
            with k3: card_kpi("MARGEN ALERTA", margen_alerta, color_alerta)
            with k4: card_kpi("% Cobertura", pct_alerta, "border-blue", formato="percent")
            
            st.divider()
            
            st.markdown("#### 📥 Flujo de Ingresos")
            i1, i2 = st.columns(2)
            with i1: card_kpi("Facturado (Real)", total_fact, "border-green")
            with i2: card_kpi("Por Facturar (Pendiente)", total_pend, "border-gray")
            
            st.divider()

            # LADO A LADO (IZQ: FIRMES / DER: TRANSITORIOS)
            c_izq, c_der = st.columns(2)
            
            with c_izq:
                st.markdown("#### 📚 Costos Firmes (Contables - YA CERRADOS)")
                st.caption("Estos costos NO restan en el semáforo de alerta.")
                card_kpi("Instalación", totales['Instalación'], "border-orange")
                card_kpi("Suministros", totales['Suministros'], "border-orange")
                card_kpi("Costo Venta (Retail)", totales['Costo Retail'], "border-orange")
                card_kpi("Ajustes Inv.", totales['Ajustes Inv'], "border-gray")
                card_kpi("Otros Gastos", totales['Otros Gastos'], "border-gray")

            with c_der:
                st.markdown("#### ⚙️ Costos Transitorios (Vivos - ALERTA)")
                st.caption("Estos costos SÍ restan en el semáforo.")
                card_kpi("Inventario en Sitio", df_s['Valor_Total'].sum() if not df_s.empty else 0, "border-purple")
                card_kpi("WIP (En Proceso)", totales['WIP'], "border-yellow")
                card_kpi("Compras Pendientes", df_c['Monto_Pendiente'].sum() if not df_c.empty else 0, "border-teal")
                card_kpi("Mano de Obra (Horas)", df_h['Costo'].sum() if not df_h.empty else 0, "border-blue")
                st.markdown("---")
                card_kpi("Provisiones (Informativo)", totales['Provisión'], "border-purple", "Reserva contable (No suma)") 
            
            st.divider()
            t1, t2, t3, t4 = st.tabs(["Inventario", "Compras", "Contabilidad", "Fact. Pend."])
            with t1: st.dataframe(df_s, use_container_width=True)
            with t2: st.dataframe(df_c, use_container_width=True)
            with t3: st.dataframe(df_f, use_container_width=True)
            with t4: st.dataframe(df_fe, use_container_width=True)

# === PESTAÑA 3: PRODUCTOS (ACTUALIZADA: Métrica + Categoría + Zona) ===
with tab_prod:
    df_cat = cargar_inventario_general()
    if not df_prod.empty:
        # --- 1. FILTROS GENERALES ---
        c_f1, c_f2 = st.columns([1, 4])
        with c_f1: 
            anio = st.selectbox("📅 Año", sorted(df_prod['date'].dt.year.unique(), reverse=True))
        with c_f2: 
            # Selector de métrica (Afecta a TODOS los gráficos)
            tipo_ver = st.radio("📊 Ver Gráficos por:", 
                                ["Monto (₡)", "Cantidad (Und)", "Freq. Facturas (# Docs)"], 
                                index=0, horizontal=True)
        
        # --- CONFIGURACIÓN DINÁMICA ---
        if "Monto" in tipo_ver:
            col_calc = 'Venta_Neta'
            agg_func = 'sum'
            fmt_text = '.2s'
        elif "Cantidad" in tipo_ver:
            col_calc = 'quantity'
            agg_func = 'sum'
            fmt_text = '.2s'
        else:
            col_calc = 'ID_Factura'
            agg_func = 'nunique' # Conteo único de facturas
            fmt_text = ''
        
        # Filtrar datos base por año
        df_p = df_prod[df_prod['date'].dt.year == anio].merge(df_cat[['ID_Producto','Tipo']], on='ID_Producto', how='left').fillna({'Tipo':'Otro'})
        
        # --- 2. GRÁFICOS GLOBALES ---
        c_m1, c_m2 = st.columns([1, 2])
        
        # Mix por Tipo
        grp_tipo = df_p.groupby('Tipo')[col_calc].agg(agg_func).reset_index()
        with c_m1: 
            fig_pie = px.pie(grp_tipo, values=col_calc, names='Tipo', 
                             title=f"Mix por Tipo ({tipo_ver})", 
                             height=400)
            
            # Ajustes de diseño:
            fig_pie.update_layout(
                # title_pad: Agrega espacio (b=bottom) debajo del título
                title_pad=dict(b=50), 
                # margin: Aumentamos el margen superior (t=top) para que quepa el título más separado
                margin=dict(t=50, b=10, l=10, r=10)
            )
            
            st.plotly_chart(config_plotly(fig_pie), use_container_width=True)
        
        # Top 10 Global
        grp_top = df_p.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
        with c_m2: 
            st.plotly_chart(config_plotly(px.bar(grp_top, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, title=f"Top 10 Global ({tipo_ver})")), use_container_width=True)

        # --- PREPARACIÓN DE DATOS DETALLADOS ---
        if not df_main.empty:
            # Cruzamos productos con clientes para traer Categoría y Zona de una sola vez
            df_merged = pd.merge(df_p, df_main[['id', 'Categoria_Cliente', 'Zona_Comercial']], left_on='ID_Factura', right_on='id', how='left')
            df_merged['Categoria_Cliente'] = df_merged['Categoria_Cliente'].fillna("Sin Categoría")
            df_merged['Zona_Comercial'] = df_merged['Zona_Comercial'].fillna("Sin Zona")

            st.divider()
            
            # --- 3. POR CATEGORÍA DE CLIENTE ---
            c_cat1, c_cat2 = st.columns([1, 3])
            with c_cat1: 
                st.subheader(f"🛍️ Por Categoría")
                cats = sorted(df_merged['Categoria_Cliente'].unique())
                cat_sel = st.selectbox("Filtrar Categoría:", cats)
            
            with c_cat2:
                df_cf = df_merged[df_merged['Categoria_Cliente'] == cat_sel]
                if not df_cf.empty:
                    top_cat = df_cf.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
                    fig_cat = px.bar(top_cat, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {cat_sel}", color_discrete_sequence=['#8e44ad']) # Morado
                    st.plotly_chart(config_plotly(fig_cat), use_container_width=True)
                else:
                    st.info("Sin datos.")

            st.divider()

            # --- 4. POR ZONA COMERCIAL (NUEVO) ---
            c_zon1, c_zon2 = st.columns([1, 3])
            with c_zon1: 
                st.subheader(f"🌍 Por Zona")
                zonas = sorted(df_merged['Zona_Comercial'].unique())
                zona_sel = st.selectbox("Filtrar Zona:", zonas)
            
            with c_zon2:
                df_zf = df_merged[df_merged['Zona_Comercial'] == zona_sel]
                if not df_zf.empty:
                    top_zona = df_zf.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
                    fig_zona = px.bar(top_zona, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {zona_sel}", color_discrete_sequence=['#16a085']) # Teal/Verde
                    st.plotly_chart(config_plotly(fig_zona), use_container_width=True)
                else:
                    st.info("Sin datos.")

# === PESTAÑA 4: BAJA ROTACIÓN ===
with tab_inv:
    if st.button("🔄 Calcular Rotación"):
        df_h, status = cargar_inventario_baja_rotacion()
        if not df_h.empty:
            days = st.slider("Días Inactivo:", 0, 720, 365)
            df_show = df_h[df_h['Dias_Sin_Salida'] >= days]
            c1, c2, c3 = st.columns(3)
            with c1: card_kpi("Capital Estancado", df_show['Valor'].sum(), "border-red")
            with c2: card_kpi("Total Items", len(df_h), "border-gray", formato="numero")
            with c3: card_kpi("Items Críticos", len(df_show), "border-orange", formato="numero")
            st.dataframe(df_show[['Producto','Ubicacion','quantity','Dias_Sin_Salida','Valor']], use_container_width=True)
        else: st.info(status)

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    df_cx = cargar_cartera()
    if not df_cx.empty:
        deuda = df_cx['amount_residual'].sum()
        vencido = df_cx[df_cx['Dias_Vencido']>0]['amount_residual'].sum()
        c1, c2, c3 = st.columns(3)
        with c1: card_kpi("Por Cobrar", deuda, "border-blue")
        with c2: card_kpi("Vencido", vencido, "border-red")
        with c3: card_kpi("Salud", f"{(1-(vencido/deuda))*100:.1f}% al día" if deuda>0 else "100%", "border-green", formato="raw")
        c_g, c_t = st.columns([2,1])
        with c_g:
            df_b = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            st.plotly_chart(config_plotly(px.bar(df_b, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad')), use_container_width=True)
        with c_t:
            st.dataframe(df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).head(10), use_container_width=True)

# === PESTAÑA 6: SEGMENTACIÓN ===
with tab_cli:
    if not df_main.empty:
        anio_c = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sc")
        df_c = df_main[df_main['invoice_date'].dt.year == anio_c]
        c1, c2, c3 = st.columns(3)
        with c1: st.plotly_chart(config_plotly(px.pie(df_c.groupby('Provincia')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Provincia')), use_container_width=True)
        with c2: st.plotly_chart(config_plotly(px.pie(df_c.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Zona_Comercial')), use_container_width=True)
        with c3: st.plotly_chart(config_plotly(px.pie(df_c.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Categoria_Cliente')), use_container_width=True)
        st.divider()
        df_old = df_main[df_main['invoice_date'].dt.year == (anio_c - 1)]
        cli_now = set(df_c['Cliente'])
        cli_old = set(df_old['Cliente'])
        nuevos = list(cli_now - cli_old)
        perdidos = list(cli_old - cli_now)
        k1, k2, k3, k4 = st.columns(4)
        with k1: card_kpi("Activos", len(cli_now), "border-blue", formato="numero")
        with k2: card_kpi("Nuevos", len(nuevos), "border-green", formato="numero")
        with k3: card_kpi("Churn", len(perdidos), "border-red", formato="numero")
        with k4: card_kpi("Retención", f"{len(cli_old.intersection(cli_now))/len(cli_old)*100:.1f}%" if cli_old else "100%", "border-purple", formato="raw")
        c_top, c_lost = st.columns(2)
        with c_top:
            st.subheader("Top Clientes")
            df_top = df_c.groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
            st.plotly_chart(config_plotly(px.bar(df_top, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
        with c_lost:
            st.subheader("Oportunidad (Perdidos)")
            if perdidos:
                df_l = df_old[df_old['Cliente'].isin(perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(config_plotly(px.bar(df_l, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        c1, c2 = st.columns(2)
        with c1: anio_v = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sv")
        with c2: vend = st.selectbox("Vendedor", sorted(df_main['Vendedor'].unique()))
        df_v = df_main[(df_main['invoice_date'].dt.year == anio_v) & (df_main['Vendedor'] == vend)]
        df_v_old = df_main[(df_main['invoice_date'].dt.year == (anio_v-1)) & (df_main['Vendedor'] == vend)]
        perdidos_v = list(set(df_v_old['Cliente']) - set(df_v['Cliente']))
        k1, k2, k3 = st.columns(3)
        with k1: card_kpi("Venta", df_v['Venta_Neta'].sum(), "border-green")
        with k2: card_kpi("Clientes", df_v['Cliente'].nunique(), "border-blue", formato="numero")
        with k3: card_kpi("Riesgo", len(perdidos_v), "border-red", formato="numero")
        c_v1, c_v2 = st.columns(2)
        with c_v1:
            st.subheader("Mejores Clientes")
            if not df_v.empty:
                df_best = df_v.groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(config_plotly(px.bar(df_best, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
        with c_v2:
            st.subheader("Cartera Perdida")
            if perdidos_v:
                df_lst = df_v_old[df_v_old['Cliente'].isin(perdidos_v)].groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(config_plotly(px.bar(df_lst, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 8: RADIOGRAFÍA ===
with tab_det:
    if not df_main.empty:
        cli = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()), index=None, placeholder="Escriba para buscar...")
        if cli:
            df_cl = df_main[df_main['Cliente'] == cli]
            ultima = df_cl['invoice_date'].max()
            dias = (datetime.now() - ultima).days
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Total Histórico", df_cl['Venta_Neta'].sum(), "border-green")
            with k2: card_kpi("Última Compra", ultima.strftime('%d-%m-%Y'), "border-blue", formato="raw")
            with k3: card_kpi("Días Inactivo", dias, "border-red" if dias>90 else "border-gray", formato="numero")
            with k4: card_kpi("Ubicación", df_cl.iloc[0]['Provincia'], "border-purple", formato="raw")
            c_h, c_p = st.columns(2)
            with c_h:
                st.subheader("Historial")
                hist = df_cl.groupby(df_cl['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                st.plotly_chart(config_plotly(px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s')), use_container_width=True)
            with c_p:
                st.subheader("Top Productos")
                if not df_prod.empty:
                    df_cp = df_prod[df_prod['ID_Factura'].isin(df_cl['id'])]
                    top = df_cp.groupby('Producto')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                    st.plotly_chart(config_plotly(px.bar(top, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s')), use_container_width=True)



















