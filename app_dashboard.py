import streamlit as st
import pandas as pd
import xmlrpc.client
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import io
import os
import ast

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Alrotek Sales Monitor", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .block-container {padding-top: 1rem; padding-bottom: 1rem;}
            
            .kpi-card {
                padding: 15px;
                border-radius: 10px;
                color: white;
                text-align: center;
                margin-bottom: 10px;
                box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
                min-height: 100px;
            }
            .kpi-title { font-size: 0.8rem; font-weight: bold; opacity: 0.9; min-height: 35px; align-items: center; display: flex; justify-content: center;}
            .kpi-value { font-size: 1.3rem; font-weight: bold; margin-top: 5px; }
            .kpi-note { font-size: 0.7rem; opacity: 0.9; margin-top: 5px; font-style: italic;}
            
            /* PALETA */
            .bg-green { background-color: #27ae60; }   /* Ventas */
            .bg-orange { background-color: #d35400; }  /* Costo Retail */
            .bg-yellow { background-color: #f1c40f; color: #333 !important; }  /* WIP */
            .bg-blue { background-color: #2980b9; }    /* Instalación */
            .bg-purple { background-color: #8e44ad; }  /* Inventario */
            .bg-red { background-color: #c0392b; }     /* Provisiones */
            .bg-teal { background-color: #16a085; }    /* Compras */
            .bg-cyan { background-color: #1abc9c; }    /* Proyección Facturación */
            .bg-gray { background-color: #7f8c8d; }    /* Ajustes/Otros */
            .bg-light-orange { background-color: #f39c12; } /* Suministros */
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- 2. CREDENCIALES & CUENTAS ---
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    COMPANY_ID = st.secrets["odoo"]["company_id"]
    
    # IDs CONTABLES
    IDS_INGRESOS = [58, 384]     
    ID_COSTO_RETAIL = 76         
    ID_COSTO_INSTALACION = 399   
    ID_SUMINISTROS_PROY = 400    
    ID_WIP = 503                 
    ID_PROVISION_PROY = 504      
    ID_AJUSTES_INV = 395         
    
    TODOS_LOS_IDS = IDS_INGRESOS + [ID_WIP, ID_PROVISION_PROY, ID_COSTO_INSTALACION, ID_SUMINISTROS_PROY, ID_AJUSTES_INV, ID_COSTO_RETAIL]
    
except Exception:
    st.error("❌ Error: No encuentro el archivo .streamlit/secrets.toml")
    st.stop()

# --- 3. FUNCIONES UTILITARIAS ---
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
    return output.getvalue()

def card_kpi(titulo, valor, color_class, nota=""):
    if isinstance(valor, str):
        val_fmt = valor
    else:
        val_fmt = f"₡ {valor:,.0f}"
    st.markdown(f"""
    <div class="kpi-card {color_class}">
        <div class="kpi-title">{titulo}</div>
        <div class="kpi-value">{val_fmt}</div>
        <div class="kpi-note">{nota}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 4. FUNCIONES DE CARGA ---

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
    except Exception: return pd.DataFrame()

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
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': ['date', 'product_id', 'credit', 'debit', 'quantity', 'name', 'move_id', 'analytic_distribution']})
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
    """Inventario para pestaña Productos"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        try: ids_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
        except: ids_kits = []
        dominio = [['active', '=', True]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'create_date', 'default_code']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['create_date'] = pd.to_datetime(df['create_date'])
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_baja_rotacion():
    """
    V7.2: Inventario Baja Rotación.
    - Filtra BP/Stock.
    - Excluye Kits.
    - Usa in_date (Ultimo Ingreso) para calcular antigüedad.
    - Manejo seguro de fechas y columnas.
    """
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # 1. Detectar Kits
        try:
            ids_bom_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
            data_boms = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'read', [ids_bom_kits], {'fields': ['product_tmpl_id']})
            ids_tmpl_kits = [b['product_tmpl_id'][0] for b in data_boms if b['product_tmpl_id']]
        except: ids_tmpl_kits = []
        
        # 2. Encontrar Ubicación BP/Stock
        dominio_loc = [
            ['complete_name', 'ilike', 'BP/Stock'],
            ['usage', '=', 'internal'],
            ['company_id', '=', COMPANY_ID]
        ]
        ids_locs_raiz = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [dominio_loc])
        
        if not ids_locs_raiz: 
            return pd.DataFrame(), "❌ No se encontró ubicación 'BP/Stock'."
            
        info_locs = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [ids_locs_raiz], {'fields': ['complete_name']})
        nombres_bodegas = [l['complete_name'] for l in info_locs]

        # 3. Buscar Quants
        dominio_quant = [
            ['location_id', 'child_of', ids_locs_raiz], 
            ['quantity', '>', 0],
            ['company_id', '=', COMPANY_ID]
        ]
        campos_quant = ['product_id', 'quantity', 'location_id', 'in_date', 'create_date']
        
        ids_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [dominio_quant])
        data_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [ids_quants], {'fields': campos_quant})
        
        df = pd.DataFrame(data_quants)
        if df.empty: return pd.DataFrame(), f"Bodegas ({nombres_bodegas}) vacías."
        
        # 4. Procesamiento
        df['pid'] = df['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
        df['Producto'] = df['product_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "Desc.")
        df['Ubicacion'] = df['location_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "-")
        
        # --- FECHAS ---
        df['Fecha_Base'] = pd.to_datetime(df['in_date'], errors='coerce')
        df['Fecha_Creacion'] = pd.to_datetime(df['create_date'], errors='coerce')
        df['Fecha_Referencia'] = df['Fecha_Base'].fillna(df['Fecha_Creacion'])
        df['Fecha_Referencia'] = df['Fecha_Referencia'].fillna(pd.Timestamp('2020-01-01'))
        
        # 5. Traer Costos
        ids_prods = df['pid'].unique().tolist()
        prod_details = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids_prods], {'fields': ['standard_price', 'product_tmpl_id']})
        df_prod_info = pd.DataFrame(prod_details)
        df_prod_info['Costo'] = df_prod_info['standard_price']
        df_prod_info['tmpl_id'] = df_prod_info['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
        
        df = pd.merge(df, df_prod_info[['id', 'Costo', 'tmpl_id']], left_on='pid', right_on='id', how='left')
        
        if ids_tmpl_kits:
            df = df[~df['tmpl_id'].isin(ids_tmpl_kits)]
        
        df['Valor'] = df['quantity'] * df['Costo']

        # 6. AGRUPAR
        # IMPORTANTE: join de ubicaciones para no perderlas
        df_agrupado = df.groupby(['Producto']).agg({
            'quantity': 'sum',
            'Valor': 'sum',
            'Fecha_Referencia': 'max',
            'Ubicacion': lambda x: ", ".join(sorted(set(str(v) for v in x if v)))
        }).reset_index()
        
        df_agrupado['Dias_En_Bodega'] = (pd.Timestamp.now() - df_agrupado['Fecha_Referencia']).dt.days
        df_huesos = df_agrupado.sort_values('Dias_En_Bodega', ascending=False)
        
        return df_huesos, f"Filtro: {', '.join(nombres_bodegas)}"

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
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_pnl_historico():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        ids_gastos = models.execute_kw(DB, uid, PASSWORD, 'account.account', 'search', [[['code', '=like', '6%']]])
        ids_totales = list(set(TODOS_LOS_IDS + ids_gastos))
        
        dominio_pnl = [
            ['account_id', 'in', ids_totales],
            ['company_id', '=', COMPANY_ID], 
            ['parent_state', '=', 'posted'], 
            ['analytic_distribution', '!=', False]
        ]
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
    except Exception: return pd.DataFrame()

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
        campos = ['date', 'account_id', 'amount', 'unit_amount', 'x_studio_tipo_horas_1', 'name', 'employee_id']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.line', 'read', [ids], {'fields': campos})
        df = pd.DataFrame(registros)
        if not df.empty:
            def limpiar_tipo(val): return str(val) if val else "No Definido"
            df['Tipo_Hora'] = df['x_studio_tipo_horas_1'].apply(limpiar_tipo)
            df['Empleado'] = df['employee_id'].apply(lambda x: x[1] if x else "Desconocido")
            def get_multiplier(tipo):
                t = tipo.lower()
                if "doble" in t: return 3.0
                if "extra" in t: return 1.5
                return 1.0
            df['Multiplicador'] = df['Tipo_Hora'].apply(get_multiplier)
            df['Costo_Base'] = df['amount'].abs()
            df['Costo'] = df['Costo_Base'] * df['Multiplicador']
            df['Horas'] = df['unit_amount']
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_inventario_ubicacion_proyecto_v4(ids_cuentas_analiticas, nombres_cuentas_analiticas):
    try:
        if not ids_cuentas_analiticas: return pd.DataFrame(), "SIN_SELECCION", []
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_analytic_clean = [int(x) for x in ids_cuentas_analiticas if pd.notna(x) and x != 0]
        ids_projects = []
        if ids_analytic_clean:
            try: ids_found = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', ids_analytic_clean]]])
            except: pass
        ids_search = list(set(ids_analytic_clean + ids_projects))
        ids_locs_studio = []
        if ids_search: ids_locs_studio = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', 'in', ids_search]]])
        ids_locs_name = []
        if nombres_cuentas_analiticas:
            for nombre in nombres_cuentas_analiticas:
                if isinstance(nombre, str) and len(nombre) > 4:
                    keyword = nombre.split(' ')[0] 
                    if len(keyword) > 3:
                        found = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['name', 'ilike', keyword]]])
                        ids_locs_name.extend(found)
        ids_locs_final = list(set(ids_locs_studio + ids_locs_name))
        if not ids_locs_final: return pd.DataFrame(), "NO_BODEGA", []
        loc_names_data = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [ids_locs_final], {'fields': ['complete_name']})
        loc_names = [l['complete_name'] for l in loc_names_data]
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
        df_final = df_final[df_final['quantity'] != 0]
        return df_final, "OK", loc_names
    except Exception as e: return pd.DataFrame(), f"ERR: {str(e)}", []

@st.cache_data(ttl=900)
def cargar_compras_pendientes_v7_json_scanner(ids_cuentas_analiticas, tc_usd):
    try:
        if not ids_cuentas_analiticas: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        targets = [str(int(x)) for x in ids_cuentas_analiticas if pd.notna(x) and x != 0]
        if not targets: return pd.DataFrame()
        dominio = [['state', 'in', ['purchase', 'done']], ['company_id', '=', COMPANY_ID], ['date_order', '>=', '2023-01-01']]
        ids = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'search', [dominio])
        campos = ['order_id', 'partner_id', 'name', 'product_qty', 'qty_invoiced', 'price_unit', 'analytic_distribution', 'currency_id']
        registros = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [ids], {'fields': campos})
        df = pd.DataFrame(registros)
        if df.empty: return pd.DataFrame()
        def es_mi_proyecto(dist):
            if not dist: return False
            try:
                d = dist if isinstance(dist, dict) else ast.literal_eval(str(dist))
                keys = [str(k) for k in d.keys()]
                for t in targets:
                    if t in keys: return True
                return False
            except: return False
        df['Es_Mio'] = df['analytic_distribution'].apply(es_mi_proyecto)
        df_filtrado = df[df['Es_Mio']].copy()
        if df_filtrado.empty: return pd.DataFrame()
        df_filtrado['qty_pending'] = df_filtrado['product_qty'] - df_filtrado['qty_invoiced']
        df_filtrado = df_filtrado[df_filtrado['qty_pending'] > 0]
        if df_filtrado.empty: return pd.DataFrame()
        def get_monto_local(row):
            monto_original = row['qty_pending'] * row['price_unit']
            moneda = row['currency_id'][1] if row['currency_id'] else "CRC"
            if moneda == 'USD': return monto_original * tc_usd
            return monto_original
        df_filtrado['Monto_Pendiente'] = df_filtrado.apply(get_monto_local, axis=1)
        df_filtrado['Proveedor'] = df_filtrado['partner_id'].apply(lambda x: x[1] if x else "-")
        df_filtrado['OC'] = df_filtrado['order_id'].apply(lambda x: x[1] if x else "-")
        return df_filtrado[['OC', 'Proveedor', 'name', 'Monto_Pendiente']]
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=900)
def cargar_facturacion_estimada_v2(ids_projects, tc_usd):
    try:
        if not ids_projects: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        ids_clean = [int(x) for x in ids_projects if pd.notna(x) and x != 0]
        if not ids_clean: return pd.DataFrame()
        proyectos_data = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'read', [ids_clean], {'fields': ['name']})
        nombres_proyectos = [p['name'] for p in proyectos_data if p['name']]
        if not nombres_proyectos: return pd.DataFrame()
        nombre_buscar = nombres_proyectos[0] 
        dominio = [['x_studio_field_sFPxe', 'ilike', nombre_buscar], ['x_studio_facturado', '=', False]]
        campos = ['x_name', 'x_Monto', 'x_Fecha'] 
        ids = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'read', [ids], {'fields': campos})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Monto_CRC'] = df['x_Monto'] * tc_usd
            df['Hito'] = df['x_name'] if 'x_name' in df.columns else "Hito"
            return df
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

def cargar_metas():
    """Función restaurada V7.0"""
    if os.path.exists("metas.xlsx"):
        df = pd.read_excel("metas.xlsx")
        df['Mes'] = pd.to_datetime(df['Mes'])
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})

# --- 5. INTERFAZ ---
st.title("🚀 Monitor Comercial ALROTEK v7.2")

with st.sidebar:
    st.header("⚙️ Configuración")
    tc_usd = st.number_input("Tipo de Cambio (USD -> CRC)", value=515, min_value=1)
    st.info(f"Usando TC: ₡{tc_usd}")

tab_kpis, tab_prod, tab_renta, tab_inv, tab_cx, tab_cli, tab_vend, tab_det = st.tabs([
    "📊 Visión General", 
    "📦 Productos", 
    "📈 Control Proyectos", 
    "📦 Baja Rotación", 
    "💰 Cartera",
    "👥 Segmentación",
    "💼 Vendedores",
    "🔍 Radiografía"
])

with st.spinner('Sincronizando todo...'):
    df_main = cargar_datos_generales()
    df_prod = cargar_detalle_productos()
    df_cat = cargar_inventario_general()
    df_metas = cargar_metas()
    df_analitica = cargar_estructura_analitica()
    
    if not df_main.empty:
        ids_unicos = df_main['ID_Cliente'].unique().tolist()
        df_info = cargar_datos_clientes_extendido(ids_unicos)
        if not df_info.empty:
            df_main = pd.merge(df_main, df_info, on='ID_Cliente', how='left')
            df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']] = df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']].fillna('Sin Dato')
        else:
            df_main['Provincia'] = 'Sin Dato'

# === PESTAÑA 1: GENERAL ===
with tab_kpis:
    if not df_main.empty:
        anios = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        anio_sel = st.selectbox("Año Fiscal (Principal)", anios, key="kpi_anio")
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
        c1.metric("Venta Total", f"₡ {venta/1e6:,.1f} M", f"{delta_anual:.1f}% vs {anio_ant}")
        c2.metric("Meta Anual", f"₡ {meta/1e6:,.1f} M")
        c3.metric("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%")
        c4.metric("Ticket Promedio", f"₡ {ticket_promedio:,.0f}", f"{cant_facturas} Ops")
        st.divider()
        col_down, _ = st.columns([1, 4])
        with col_down:
            excel_data = convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'Provincia', 'Vendedor', 'Venta_Neta']])
            st.download_button("📥 Descargar Detalle Facturas", data=excel_data, file_name=f"Ventas_{anio_sel}.xlsx")
        c_graf, c_vend = st.columns([2, 1])
        with c_graf:
            st.subheader("📊 Ventas por Plan Analítico")
            if not df_prod.empty:
                df_lineas = df_prod[df_prod['date'].dt.year == anio_sel].copy()
                mapa_planes = {}
                if not df_analitica.empty:
                    mapa_planes = dict(zip(df_analitica['id_cuenta_analitica'].astype(str), df_analitica['Plan_Nombre']))
                def clasificar_plan_estricto(dist):
                    if not dist: return "Sin Analítica (Retail)"
                    try:
                        d = dist if isinstance(dist, dict) else ast.literal_eval(str(dist))
                        if not d: return "Sin Analítica (Retail)"
                        for k in d.keys():
                            plan = mapa_planes.get(str(k))
                            if plan: return plan
                    except: pass
                    return "Analítica Desconocida"
                df_lineas['Plan_Agrupado'] = df_lineas['analytic_distribution'].apply(clasificar_plan_estricto)
                ventas_linea = df_lineas.groupby('Plan_Agrupado')['Venta_Neta'].sum().reset_index()
                fig_pie = px.pie(ventas_linea, values='Venta_Neta', names='Plan_Agrupado', hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                st.plotly_chart(fig_pie, use_container_width=True)
                st.subheader("📅 Evolución Mensual por Plan")
                df_lineas['Mes_Nombre'] = df_lineas['date'].dt.strftime('%m-%b')
                df_lineas['Mes_Num'] = df_lineas['date'].dt.month
                ventas_mes_plan = df_lineas.groupby(['Mes_Num', 'Mes_Nombre', 'Plan_Agrupado'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                total_por_mes = df_lineas.groupby(['Mes_Num', 'Mes_Nombre'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                total_por_mes['Label'] = total_por_mes['Venta_Neta'].apply(lambda x: f"₡{x/1e6:.1f}M")
                fig_stack = px.bar(ventas_mes_plan, x='Mes_Nombre', y='Venta_Neta', color='Plan_Agrupado', title="Mix de Ventas Mensual", color_discrete_sequence=px.colors.qualitative.Prism)
                fig_stack.add_trace(go.Scatter(x=total_por_mes['Mes_Nombre'], y=total_por_mes['Venta_Neta'], text=total_por_mes['Label'], mode='text', textposition='top center', textfont=dict(size=11, color='black'), showlegend=False))
                fig_stack.update_layout(height=450, barmode='stack', xaxis_title="", yaxis_title="Venta Total")
                st.plotly_chart(fig_stack, use_container_width=True)
            else: st.info("Sin datos de productos.")
            st.divider()
            v_mes_act = df_anio.groupby('Mes_Num')['Venta_Neta'].sum().reset_index()
            v_mes_act.columns = ['Mes_Num', 'Venta_Actual']
            v_mes_ant = df_ant_data.groupby('Mes_Num')['Venta_Neta'].sum().reset_index()
            v_mes_ant.columns = ['Mes_Num', 'Venta_Anterior']
            v_metas = metas_filtradas.groupby('Mes_Num')['Meta'].sum().reset_index()
            df_chart = pd.DataFrame({'Mes_Num': range(1, 13)})
            df_chart = pd.merge(df_chart, v_mes_ant, on='Mes_Num', how='left').fillna(0)
            df_chart = pd.merge(df_chart, v_mes_act, on='Mes_Num', how='left').fillna(0)
            df_chart = pd.merge(df_chart, v_metas, on='Mes_Num', how='left').fillna(0)
            nombres_meses = {1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic'}
            df_chart['Mes_Nombre'] = df_chart['Mes_Num'].map(nombres_meses)
            def get_color(real, meta):
                if meta == 0: return '#2980b9'
                if real > meta: return '#27ae60'
                if real < meta: return '#c0392b'
                return '#f1c40f'
            colores_meta = [get_color(r, m) for r, m in zip(df_chart['Venta_Actual'], df_chart['Meta'])]
            st.subheader(f"🎯 Comparativo vs Meta ({anio_sel})")
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(x=df_chart['Mes_Nombre'], y=df_chart['Venta_Actual'], name='Venta Real', marker_color=colores_meta))
            fig1.add_trace(go.Scatter(x=df_chart['Mes_Nombre'], y=df_chart['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
            fig1.update_layout(template="plotly_white", height=350, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig1, use_container_width=True)
        with c_vend:
            st.subheader("🏆 Top Vendedores")
            rank_actual = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index()
            rank_actual.columns = ['Vendedor', 'Venta_Actual']
            rank_anterior = df_ant_data.groupby('Vendedor')['Venta_Neta'].sum().reset_index()
            rank_anterior.columns = ['Vendedor', 'Venta_Anterior']
            rank_final = pd.merge(rank_actual, rank_anterior, on='Vendedor', how='left').fillna(0)
            rank_final = rank_final.sort_values('Venta_Actual', ascending=True).tail(10)
            def crear_texto(row):
                monto = f"₡{row['Venta_Actual']/1e6:.1f}M"
                ant = row['Venta_Anterior']
                act = row['Venta_Actual']
                if ant > 0:
                    delta = ((act - ant) / ant) * 100
                    icono = "⬆️" if delta >= 0 else "⬇️"
                    return f"{monto} {icono} {delta:.0f}%"
                elif act > 0: return f"{monto} ✨ New"
                return monto
            rank_final['Texto'] = rank_final.apply(crear_texto, axis=1)
            fig_v = go.Figure(go.Bar(x=rank_final['Venta_Actual'], y=rank_final['Vendedor'], orientation='h', text=rank_final['Texto'], textposition='auto', marker_color='#2980b9'))
            fig_v.update_layout(height=600, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_v, use_container_width=True)

# === PESTAÑA 2: PRODUCTOS ===
with tab_prod:
    if not df_prod.empty and not df_cat.empty:
        anios_p = sorted(df_prod['date'].dt.year.unique(), reverse=True)
        anio_p_sel = st.selectbox("Año de Análisis", anios_p, key="prod_anio")
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_p_sel].copy()
        df_p_anio = pd.merge(df_p_anio, df_cat[['ID_Producto', 'Tipo', 'Referencia']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]
        col_down_p, _ = st.columns([1, 4])
        with col_down_p:
            df_export_prod = df_p_anio.groupby(['Referencia', 'Producto', 'Tipo'])[['quantity', 'Venta_Neta']].sum().reset_index()
            excel_prod = convert_df_to_excel(df_export_prod)
            st.download_button("📥 Descargar Detalle Productos", data=excel_prod, file_name=f"Productos_Vendidos_{anio_p_sel}.xlsx")
        col_tipo1, col_tipo2 = st.columns([1, 2])
        with col_tipo1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(height=350, title_text="Mix de Venta")
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_tipo2:
            st.markdown(f"**Top 10 Productos ({anio_p_sel})**")
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                tipo_ver = st.radio("Filtrar Tipo:", ["Todos", "Almacenable", "Servicio"], horizontal=True)
            with c_f2:
                metrica_prod = st.radio("Ordenar por:", ["Monto (₡)", "Cantidad (Unid.)"], horizontal=True)
            df_show = df_p_anio if tipo_ver == "Todos" else df_p_anio[df_p_anio['Tipo'] == tipo_ver]
            top_prod = df_show.groupby('Producto')[['Venta_Neta', 'quantity']].sum().reset_index()
            col_orden = 'Venta_Neta' if metrica_prod == "Monto (₡)" else 'quantity'
            color_scale = 'Viridis' if metrica_prod == "Monto (₡)" else 'Bluyl'
            top_10 = top_prod.sort_values(col_orden, ascending=False).head(10).sort_values(col_orden, ascending=True)
            fig_bar = px.bar(top_10, x=col_orden, y='Producto', orientation='h', text_auto='.2s', color=col_orden, color_continuous_scale=color_scale)
            fig_bar.update_layout(height=350, xaxis_title=metrica_prod, yaxis_title="")
            st.plotly_chart(fig_bar, use_container_width=True)

# === PESTAÑA 3: RENTABILIDAD (CONTROL PROJECT) ===
with tab_renta:
    
    with st.spinner('Analizando Histórico P&L...'):
        df_pnl = cargar_pnl_historico()
    
    if not df_analitica.empty:
        mapa_cuentas = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Plan_Nombre']))
        mapa_nombres = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Cuenta_Nombre']))
        
        lista_planes = sorted(list(set(mapa_cuentas.values())))
        
        st.subheader("🕵️ Buscador de Proyectos (Histórico)")
        c_filt1, c_filt2 = st.columns(2)
        with c_filt1:
            planes_sel = st.multiselect("1. Selecciona Planes:", lista_planes, default=[])
            
        if planes_sel:
            ids_cuentas_posibles = [id_c for id_c, plan in mapa_cuentas.items() if plan in planes_sel]
            nombres_cuentas_posibles = [mapa_nombres[id_c] for id_c in ids_cuentas_posibles]
            
            with c_filt2:
                cuentas_sel_nombres = st.multiselect("2. Selecciona Analíticas (Opcional):", sorted(nombres_cuentas_posibles), default=sorted(nombres_cuentas_posibles))
            
            ids_seleccionados = [id_c for id_c, nombre in mapa_nombres.items() if nombre in cuentas_sel_nombres]
            
            # Buscar IDs de Proyectos (Bridge Analytic -> Project) para usar en modelo facturas
            ids_projects = []
            try:
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
                uid = common.authenticate(DB, USERNAME, PASSWORD, {})
                models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
                ids_found = models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', ids_seleccionados]]])
                ids_projects = ids_found
            except: pass

            df_filtered = pd.DataFrame()
            if not df_pnl.empty:
                df_filtered = df_pnl[df_pnl['id_cuenta_analitica'].isin(ids_seleccionados)].copy()
            
            # --- CALCULOS ---
            total_ventas = 0
            total_instalacion = 0
            total_suministros = 0
            total_wip = 0
            total_provision = 0
            total_ajustes = 0
            total_costo_retail = 0
            total_otros = 0

            if not df_filtered.empty:
                total_ventas = abs(df_filtered[df_filtered['Clasificacion'] == 'Venta']['Monto_Neto'].sum())
                total_instalacion = abs(df_filtered[df_filtered['Clasificacion'] == 'Instalación']['Monto_Neto'].sum())
                total_suministros = abs(df_filtered[df_filtered['Clasificacion'] == 'Suministros']['Monto_Neto'].sum())
                total_wip = abs(df_filtered[df_filtered['Clasificacion'] == 'WIP']['Monto_Neto'].sum())
                total_provision = abs(df_filtered[df_filtered['Clasificacion'] == 'Provisión']['Monto_Neto'].sum())
                total_ajustes = df_filtered[df_filtered['Clasificacion'] == 'Ajustes Inv']['Monto_Neto'].sum()
                total_costo_retail = abs(df_filtered[df_filtered['Clasificacion'] == 'Costo Retail']['Monto_Neto'].sum())
                
                # Otros (Gastos 6%)
                df_otros_filtrado = df_filtered[df_filtered['Clasificacion'] == 'Otros Gastos']
                total_otros = abs(df_otros_filtrado['Monto_Neto'].sum())

            # Horas (Mes Actual)
            df_horas_detalle = cargar_detalle_horas_mes(ids_seleccionados)
            total_horas_ajustado = df_horas_detalle['Costo'].sum() if not df_horas_detalle.empty else 0
            
            # Inventario Baja Rotación (Corrected variable name)
            with st.spinner("Analizando inventario..."):
                 df_huesos, msg_status = cargar_inventario_baja_rotacion()
                 # We don't use df_huesos here, we need inventory *of the project*
            
            # Project Inventory (V4)
            df_stock_sitio, status_stock, bodegas_encontradas = cargar_inventario_ubicacion_proyecto_v4(ids_seleccionados, cuentas_sel_nombres)
            total_stock_sitio = df_stock_sitio['Valor_Total'].sum() if not df_stock_sitio.empty else 0
            
            df_compras = cargar_compras_pendientes_v7_json_scanner(ids_seleccionados, tc_usd)
            total_compras_pendientes = df_compras['Monto_Pendiente'].sum() if not df_compras.empty else 0
            
            # --- NUEVA CARGA: FACTURACIÓN ESTIMADA ---
            df_fact_estimada = cargar_facturacion_estimada_v2(ids_projects, tc_usd)
            total_fact_pendiente = df_fact_estimada['Monto_CRC'].sum() if not df_fact_estimada.empty else 0
            
            txt_bodegas = "Sin ubicación asignada"
            color_bg = "bg-purple"
            if status_stock == "OK" or status_stock == "NO_STOCK":
                txt_bodegas = f"Encontradas: {', '.join(bodegas_encontradas)}"
            elif "ERR" in status_stock:
                color_bg = "bg-red"
            elif status_stock == "NO_BODEGA":
                color_bg = "bg-gray"
            
            # --- FILA 1 ---
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Ventas (Acum)", total_ventas, "bg-green")
            with k2: card_kpi("Instalación (Acum)", total_instalacion, "bg-blue")
            with k3: card_kpi("Suministros (Acum)", total_suministros, "bg-light-orange")
            with k4: card_kpi("WIP Acumulado", total_wip, "bg-yellow")
            
            # --- FILA 2 ---
            k5, k6, k7, k8 = st.columns(4)
            with k5: card_kpi("Provisiones (Acum)", total_provision, "bg-red")
            with k6: card_kpi("Ajustes Inv.", total_ajustes, "bg-gray")
            with k7: card_kpi("Costo Retail", total_costo_retail, "bg-orange") 
            with k8: card_kpi("Otros (Gastos 6%)", total_otros, "bg-gray")
            
            # --- FILA 3 (KPIs Operativos) ---
            k9, k10, k11, k12 = st.columns(4)
            with k9: card_kpi("Inventario Sitio", total_stock_sitio, color_bg, nota=txt_bodegas)
            with k10: card_kpi("Compras Pendientes", total_compras_pendientes, "bg-teal")
            with k11: card_kpi("Costo Horas (Mes Actual)", total_horas_ajustado, "bg-blue")
            with k12: card_kpi("Fact. Pendiente Estimada", total_fact_pendiente, "bg-cyan", nota="Proyección futura")
            
            st.divider()
            
            c_horas, c_stock = st.columns(2)
            with c_horas:
                st.markdown("##### 🕒 Desglose de Horas (Mes Actual)")
                if not df_horas_detalle.empty:
                    resumen_horas = df_horas_detalle.groupby(['Tipo_Hora', 'Multiplicador'])[['Horas', 'Costo']].sum().reset_index()
                    st.dataframe(resumen_horas, column_config={"Costo": st.column_config.NumberColumn(format="₡ %.2f"), "Multiplicador": st.column_config.NumberColumn(format="x %.1f")}, hide_index=True, use_container_width=True)
                else: st.caption("Sin registros este mes.")
            
            with c_stock:
                st.markdown("##### 📦 Detalle Inventario / Compras")
                tab_inv_det, tab_com_det, tab_fact_det = st.tabs(["Inventario Físico", "Compras Pendientes", "Fact. Pendiente"])
                with tab_inv_det:
                    if not df_stock_sitio.empty:
                        st.dataframe(df_stock_sitio[['pname', 'quantity', 'Valor_Total']], column_config={"pname": "Producto", "Valor_Total": st.column_config.NumberColumn(format="₡ %.2f")}, hide_index=True, use_container_width=True)
                    else: st.caption(f"Estado: {status_stock}")
                with tab_com_det:
                    if not df_compras.empty:
                        st.dataframe(df_compras, column_config={"Monto_Pendiente": st.column_config.NumberColumn(format="₡ %.2f")}, hide_index=True, use_container_width=True)
                    else: st.caption("Todo facturado.")
                with tab_fact_det:
                    if not df_fact_estimada.empty:
                        st.dataframe(df_fact_estimada[['Hito', 'x_Monto', 'Monto_CRC', 'x_Fecha']], 
                                     column_config={
                                         "x_Monto": st.column_config.NumberColumn("Monto USD", format="$ %.2f"),
                                         "Monto_CRC": st.column_config.NumberColumn("Monto CRC", format="₡ %.2f"),
                                         "x_Fecha": st.column_config.DateColumn("Fecha Est.", format="DD/MM/YYYY")
                                     }, hide_index=True, use_container_width=True)
                    else: st.caption("No hay hitos pendientes.")
            
            st.divider()
            st.markdown("**Detalle Movimientos Contables (Acumulado)**")
            if not df_filtered.empty:
                st.dataframe(df_filtered[['date', 'name', 'Nombre_Cuenta', 'Clasificacion', 'Monto_Neto']].sort_values(['Clasificacion', 'date'], ascending=True), column_config={"Monto_Neto": st.column_config.NumberColumn(format="₡ %.2f"), "date": st.column_config.DateColumn(format="DD/MM/YYYY")}, use_container_width=True, hide_index=True)

# === PESTAÑA 4: INVENTARIO (BAJA ROTACIÓN) ===
with tab_inv:
    with st.spinner("Calculando rotación..."):
        df_huesos, msg_status = cargar_inventario_baja_rotacion()
    
    st.subheader("📦 Análisis de Baja Rotación")
    
    if "Error" in msg_status or "No se encontró" in msg_status:
        st.error(msg_status)
    else:
        st.success(msg_status)
    
    if not df_huesos.empty:
        total_atrapado = df_huesos['Valor'].sum()
        criticos = df_huesos[df_huesos['Dias_En_Bodega'] > 365]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Valor Total en Bodega", f"₡ {total_atrapado/1e6:,.1f} M")
        m2.metric("Items Totales", len(df_huesos))
        m3.metric("Huesos Críticos (>1 año)", len(criticos), delta_color="inverse")
        
        st.divider()
        
        dias_min = st.slider("Filtrar por días mínimos de antigüedad:", 0, 720, 365)
        df_show = df_huesos[df_huesos['Dias_En_Bodega'] >= dias_min]
        
        st.dataframe(
            df_show[['Producto', 'Ubicacion', 'quantity', 'Dias_En_Bodega', 'Valor']],
            column_config={
                "Valor": st.column_config.NumberColumn(format="₡ %.2f"),
                "quantity": st.column_config.NumberColumn("Cant."),
                "Dias_En_Bodega": st.column_config.ProgressColumn("Días Quieto", min_value=0, max_value=720, format="%d días"),
                "Fecha_Referencia": st.column_config.DateColumn("Fecha Ingreso")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No hay stock disponible con los criterios seleccionados.")

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    with st.spinner('Analizando deudas...'):
        df_cx = cargar_cartera()
    if not df_cx.empty:
        total_deuda = df_cx['amount_residual'].sum()
        total_vencido = df_cx[df_cx['Dias_Vencido'] > 0]['amount_residual'].sum()
        pct_vencido = (total_vencido / total_deuda * 100) if total_deuda > 0 else 0
        kcx1, kcx2, kcx3 = st.columns(3)
        kcx1.metric("Total por Cobrar", f"₡ {total_deuda/1e6:,.1f} M")
        kcx2.metric("Cartera Vencida (>0 días)", f"₡ {total_vencido/1e6:,.1f} M")
        kcx3.metric("Salud de Cartera", f"{100-pct_vencido:.1f}% Al Día", delta_color="normal" if pct_vencido < 20 else "inverse")
        st.divider()
        col_cx_g1, col_cx_g2 = st.columns([2, 1])
        with col_cx_g1:
            st.subheader("⏳ Antigüedad de Saldos")
            df_buckets = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            colores_cx = {"Por Vencer": "#2ecc71", "0-30 Días": "#f1c40f", "31-60 Días": "#e67e22", "61-90 Días": "#e74c3c", "+90 Días": "#c0392b"}
            fig_cx = px.bar(df_buckets, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad', color_discrete_map=colores_cx)
            fig_cx.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig_cx, use_container_width=True)
        with col_cx_g2:
            st.subheader("🚨 Top Deudores")
            top_deudores = df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).head(10).reset_index()
            st.dataframe(top_deudores, column_config={"amount_residual": st.column_config.NumberColumn(format="₡ %.2f")}, hide_index=True, use_container_width=True)
        st.divider()
        col_down_cx, _ = st.columns([1, 4])
        with col_down_cx:
            excel_cx = convert_df_to_excel(df_cx[['invoice_date', 'invoice_date_due', 'name', 'Cliente', 'Vendedor', 'amount_total', 'amount_residual', 'Antiguedad']])
            st.download_button("📥 Descargar Reporte Cobros", data=excel_cx, file_name=f"Cartera_Alrotek_{datetime.now().date()}.xlsx")
    else:
        st.success("¡Felicidades! No hay cuentas por cobrar pendientes.")

# === PESTAÑA 6: SEGMENTACIÓN CLIENTES ===
with tab_cli:
    if not df_main.empty:
        st.subheader("🌍 Distribución de Ventas")
        anio_c_sel = st.selectbox("Año de Análisis", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        col_geo1, col_geo2, col_cat = st.columns(3)
        with col_geo1:
            ventas_prov = df_c_anio.groupby('Provincia')['Venta_Neta'].sum().reset_index()
            fig_prov = px.pie(ventas_prov, values='Venta_Neta', names='Provincia', hole=0.4)
            st.plotly_chart(fig_prov, use_container_width=True)
        with col_geo2:
            ventas_zona = df_c_anio.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index()
            fig_zona = px.pie(ventas_zona, values='Venta_Neta', names='Zona_Comercial', hole=0.4)
            st.plotly_chart(fig_zona, use_container_width=True)
        with col_cat:
            ventas_cat = df_c_anio.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index()
            fig_cat = px.pie(ventas_cat, values='Venta_Neta', names='Categoria_Cliente', hole=0.4)
            st.plotly_chart(fig_cat, use_container_width=True)
        st.divider()
        col_d1, col_d2, col_d3 = st.columns(3)
        df_top_all = df_c_anio.groupby(['Cliente', 'Provincia', 'Zona_Comercial'])['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
        col_d1.download_button("📂 Ranking Completo", data=convert_df_to_excel(df_top_all), file_name=f"Ranking_Clientes_{anio_c_sel}.xlsx")
        df_c_ant = df_main[df_main['invoice_date'].dt.year == (anio_c_sel - 1)]
        cli_antes = set(df_c_ant[df_c_ant['Venta_Neta'] > 0]['Cliente'])
        cli_ahora = set(df_c_anio[df_c_anio['Venta_Neta'] > 0]['Cliente'])
        lista_perdidos = list(cli_antes - cli_ahora)
        lista_nuevos = list(cli_ahora - cli_antes)
        monto_perdido = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]['Venta_Neta'].sum() if lista_perdidos else 0
        monto_nuevo = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]['Venta_Neta'].sum() if lista_nuevos else 0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Clientes Activos", len(cli_ahora))
        k2.metric("Clientes Nuevos", len(lista_nuevos))
        k3.metric("Venta de Nuevos", f"₡ {monto_nuevo/1e6:,.1f} M")
        k4.metric("Venta Perdida (Churn)", f"₡ {monto_perdido/1e6:,.1f} M", delta=-len(lista_perdidos), delta_color="inverse")
        if lista_perdidos:
            df_lost_all = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
            col_d2.download_button("📉 Lista Perdidos", data=convert_df_to_excel(df_lost_all), file_name=f"Clientes_Perdidos_{anio_c_sel}.xlsx")
        if lista_nuevos:
            df_new_all = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
            col_d3.download_button("🌱 Lista Nuevos", data=convert_df_to_excel(df_new_all), file_name=f"Clientes_Nuevos_{anio_c_sel}.xlsx")
        st.divider()
        c_top, c_analisis = st.columns([1, 1])
        with c_top:
            st.subheader("🏆 Top 10 Clientes")
            top_10 = df_c_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
            fig_top = px.bar(top_10, x='Venta_Neta', y=top_10.index, orientation='h', text_auto='.2s', color=top_10.values)
            st.plotly_chart(fig_top, use_container_width=True)
        with c_analisis:
            st.subheader("⚠️ Top Perdidos (Oportunidad)")
            if lista_perdidos:
                df_lost = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]
                top_lost = df_lost.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                fig_lost = px.bar(top_lost, x='Venta_Neta', y=top_lost.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])
                fig_lost.update_layout(xaxis_title="Compró Año Pasado")
                st.plotly_chart(fig_lost, use_container_width=True)
            else: st.success("Retención del 100%.")

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        st.header("💼 Análisis de Desempeño Individual")
        anios_v = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1: anio_v_sel = st.selectbox("Año de Evaluación", anios_v, key="vend_anio")
        with col_sel2: vendedor_sel = st.selectbox("Seleccionar Comercial", sorted(df_main['Vendedor'].unique()))
        df_v_anio = df_main[(df_main['invoice_date'].dt.year == anio_v_sel) & (df_main['Vendedor'] == vendedor_sel)]
        df_v_ant = df_main[(df_main['invoice_date'].dt.year == (anio_v_sel - 1)) & (df_main['Vendedor'] == vendedor_sel)]
        venta_ind = df_v_anio['Venta_Neta'].sum()
        facturas_ind = df_v_anio['name'].nunique()
        ticket_ind = (venta_ind / facturas_ind) if facturas_ind > 0 else 0
        cli_v_antes = set(df_v_ant[df_v_ant['Venta_Neta'] > 0]['Cliente'])
        cli_v_ahora = set(df_v_anio[df_v_anio['Venta_Neta'] > 0]['Cliente'])
        perdidos_v = list(cli_v_antes - cli_v_ahora)
        kv1, kv2, kv3, kv4 = st.columns(4)
        kv1.metric(f"Venta Total {vendedor_sel}", f"₡ {venta_ind/1e6:,.1f} M")
        kv2.metric("Clientes Activos", len(cli_v_ahora))
        kv3.metric("Ticket Promedio", f"₡ {ticket_ind:,.0f}")
        kv4.metric("Clientes en Riesgo", len(perdidos_v), delta=-len(perdidos_v), delta_color="inverse")
        st.divider()
        col_dv1, col_dv2 = st.columns(2)
        with col_dv1:
            excel_vend = convert_df_to_excel(df_v_anio[['invoice_date', 'name', 'Cliente', 'Venta_Neta']])
            st.download_button(f"📥 Descargar Ventas {vendedor_sel}", data=excel_vend, file_name=f"Ventas_{vendedor_sel}_{anio_v_sel}.xlsx")
        with col_dv2:
            if perdidos_v:
                df_llamadas = df_v_ant[df_v_ant['Cliente'].isin(perdidos_v)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
                st.download_button(f"📞 Descargar Lista Recuperación", data=convert_df_to_excel(df_llamadas), file_name=f"Recuperar_{vendedor_sel}.xlsx")
        st.divider()
        col_v_top, col_v_lost = st.columns(2)
        with col_v_top:
            st.subheader(f"🌟 Mejores Clientes")
            if not df_v_anio.empty:
                top_cli_v = df_v_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                fig_vt = px.bar(top_cli_v, x=top_cli_v.values, y=top_cli_v.index, orientation='h', text_auto='.2s', color=top_cli_v.values)
                st.plotly_chart(fig_vt, use_container_width=True)
            else: st.info("Sin ventas registradas.")
        with col_v_lost:
            st.subheader("⚠️ Cartera Perdida")
            if perdidos_v:
                df_lost_v = df_v_ant[df_v_ant['Cliente'].isin(perdidos_v)]
                top_lost_v = df_lost_v.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                fig_vl = px.bar(top_lost_v, x=top_lost_v.values, y=top_lost_v.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])
                st.plotly_chart(fig_vl, use_container_width=True)
            else: st.success(f"Excelente retención.")

# === PESTAÑA 8: RADIOGRAFÍA CLIENTE ===
with tab_det:
    if not df_main.empty:
        st.header("🔍 Radiografía Individual")
        cliente_sel = st.selectbox("Buscar cliente:", sorted(df_main['Cliente'].unique()), index=None)
        if cliente_sel:
            df_cli = df_main[df_main['Cliente'] == cliente_sel]
            total_comprado = df_cli['Venta_Neta'].sum()
            ultima_compra = df_cli['invoice_date'].max()
            dias_sin = (datetime.now() - ultima_compra).days
            provincia = df_cli.iloc[0]['Provincia'] if 'Provincia' in df_cli.columns else "N/A"
            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Compras Históricas", f"₡ {total_comprado/1e6:,.1f} M")
            kc2.metric("Última Compra", ultima_compra.strftime('%d-%m-%Y'))
            kc3.metric("Días sin Comprar", dias_sin, delta=-dias_sin, delta_color="inverse")
            kc4.metric("Ubicación", provincia)
            st.divider()
            c_hist, c_prod = st.columns([1, 1])
            with c_hist:
                hist = df_cli.groupby(df_cli['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                fig_h = px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s', title="Historial Anual")
                st.plotly_chart(fig_h, use_container_width=True)
            with c_prod:
                metrica_cli = st.radio("Ver por:", ["Monto", "Cantidad"], horizontal=True, label_visibility="collapsed")
                if not df_prod.empty:
                    ids_facturas = df_cli['id'].tolist() if 'id' in df_cli.columns else [] 
                    if not ids_facturas: ids_facturas = [] 
                    ids_cli = set(df_cli['id'])
                    df_prod_cli = df_prod[df_prod['ID_Factura'].isin(ids_cli)]
                    if not df_prod_cli.empty:
                        col_orden = 'Venta_Neta' if metrica_cli == "Monto" else 'quantity'
                        top_p = df_prod_cli.groupby('Producto')[[col_orden]].sum().sort_values(col_orden, ascending=False).head(10)
                        fig_p = px.bar(top_p, x=col_orden, y=top_p.index, orientation='h', text_auto='.2s')
                        st.plotly_chart(fig_p, use_container_width=True)
                        df_hist = df_prod_cli.groupby(['date', 'Producto'])[['quantity', 'Venta_Neta']].sum().reset_index().sort_values('date', ascending=False)
                        st.download_button("📥 Descargar Historial", data=convert_df_to_excel(df_hist), file_name=f"Historial_{cliente_sel}.xlsx")
                    else: st.info("No hay detalle de productos.")
