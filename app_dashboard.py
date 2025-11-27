import streamlit as st
import pandas as pd
import xmlrpc.client
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import io
import os
import ast

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILO ---
st.set_page_config(page_title="Alrotek Sales Monitor", layout="wide", page_icon="🚀")

# Estilos CSS Profesionales (Shadow Cards)
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .block-container {padding-top: 1rem; padding-bottom: 2rem;}
            
            /* TARJETAS KPI PRO */
            .kpi-card {
                background-color: #ffffff;
                padding: 15px 10px;
                border-radius: 8px;
                border-left: 5px solid #333;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 15px;
                text-align: center;
                transition: transform 0.2s;
            }
            .kpi-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 8px rgba(0,0,0,0.15);
            }
            .kpi-title { 
                font-size: 0.85rem; 
                color: #7f8c8d; 
                text-transform: uppercase; 
                letter-spacing: 0.5px; 
                font-weight: 600;
                margin-bottom: 5px;
                min-height: 30px;
                display: flex; align-items: center; justify-content: center;
            }
            .kpi-value { 
                font-size: 1.6rem; 
                font-weight: 700; 
                color: #2c3e50; 
                margin: 0;
            }
            .kpi-note { 
                font-size: 0.75rem; 
                color: #95a5a6; 
                margin-top: 4px; 
            }

            /* CLASES DE COLOR DE BORDE */
            .border-green { border-left-color: #27ae60 !important; }
            .border-orange { border-left-color: #d35400 !important; }
            .border-yellow { border-left-color: #f1c40f !important; }
            .border-blue { border-left-color: #2980b9 !important; }
            .border-purple { border-left-color: #8e44ad !important; }
            .border-red { border-left-color: #c0392b !important; }
            .border-teal { border-left-color: #16a085 !important; }
            .border-cyan { border-left-color: #1abc9c !important; }
            .border-gray { border-left-color: #95a5a6 !important; }
            .border-light-orange { border-left-color: #f39c12 !important; }
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

def card_kpi(titulo, valor, border_class, nota="", icon=""):
    if isinstance(valor, str):
        val_fmt = valor
    else:
        if abs(valor) >= 1_000_000:
            val_fmt = f"₡ {valor/1e6:,.1f} M"
        else:
            val_fmt = f"₡ {valor:,.0f}"
            
    html = f"""
    <div class="kpi-card {border_class}">
        <div class="kpi-title">{icon} {titulo}</div>
        <div class="kpi-value">{val_fmt}</div>
        <div class="kpi-note">{nota}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- 4. FUNCIONES DE CARGA (CORE) ---

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
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        try: ids_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
        except: ids_kits = []
        dominio = [['active', '=', True]]
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'create_date', 'default_code', 'product_tmpl_id']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['create_date'] = pd.to_datetime(df['create_date'])
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
            
            # Filtro Kits solo para visualizacion si se desea, aqui dejamos todo
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario_baja_rotacion():
    """
    V8.2: Rotación Real (Huesos).
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
        
        # 2. Ubicación BP/Stock
        dominio_loc = [['complete_name', 'ilike', 'BP/Stock'], ['usage', '=', 'internal'], ['company_id', '=', COMPANY_ID]]
        ids_locs_raiz = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [dominio_loc])
        if not ids_locs_raiz: return pd.DataFrame(), "❌ No se encontró 'BP/Stock'."
        
        info_locs = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [ids_locs_raiz], {'fields': ['complete_name']})
        nombres_bodegas = [l['complete_name'] for l in info_locs]

        # 3. Obtener Stock Actual
        dominio_quant = [['location_id', 'child_of', ids_locs_raiz], ['quantity', '>', 0], ['company_id', '=', COMPANY_ID]]
        campos_quant = ['product_id', 'quantity', 'location_id']
        ids_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'search', [dominio_quant])
        data_quants = models.execute_kw(DB, uid, PASSWORD, 'stock.quant', 'read', [ids_quants], {'fields': campos_quant})
        
        df = pd.DataFrame(data_quants)
        if df.empty: return pd.DataFrame(), "Bodega vacía."
        
        df['pid'] = df['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
        df['Producto'] = df['product_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "Desc.")
        df['Ubicacion'] = df['location_id'].apply(lambda x: x[1] if isinstance(x, (list, tuple)) else "-")
        
        # 4. Enriquecer
        ids_prods_stock = df['pid'].unique().tolist()
        prod_details = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids_prods_stock], {'fields': ['standard_price', 'product_tmpl_id', 'detailed_type']})
        df_prod_info = pd.DataFrame(prod_details)
        
        df_prod_info['Costo'] = df_prod_info['standard_price']
        df_prod_info['tmpl_id'] = df_prod_info['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
        
        df = pd.merge(df, df_prod_info[['id', 'Costo', 'tmpl_id', 'detailed_type']], left_on='pid', right_on='id', how='left')
        
        if ids_tmpl_kits: df = df[~df['tmpl_id'].isin(ids_tmpl_kits)]
        df = df[df['detailed_type'] == 'product'] # SOLO ALMACENABLES
        
        df['Valor'] = df['quantity'] * df['Costo']
        
        if df.empty: return pd.DataFrame(), "Sin productos almacenables."

        # 5. BUSCAR SALIDAS RECIENTES (Últimos 365 días)
        fecha_corte = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        ids_prods_final = df['pid'].unique().tolist()
        
        dominio_moves = [
            ['product_id', 'in', ids_prods_final],
            ['state', '=', 'done'],
            ['date', '>=', fecha_corte],
            ['location_dest_id.usage', 'in', ['customer', 'production']]
        ]
        
        ids_moves = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'search', [dominio_moves])
        data_moves = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'read', [ids_moves], {'fields': ['product_id', 'date']})
        
        df_moves = pd.DataFrame(data_moves)
        
        mapa_ult_salida = {}
        if not df_moves.empty:
            df_moves['pid'] = df_moves['product_id'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
            df_moves['date'] = pd.to_datetime(df_moves['date'])
            mapa_ult_salida = df_moves.groupby('pid')['date'].max().to_dict()
            
        # 6. Calcular Días Sin Salida
        def calc_dias(row):
            pid = row['pid']
            if pid in mapa_ult_salida:
                return (pd.Timestamp.now() - mapa_ult_salida[pid]).days
            return 366 

        df['Dias_Sin_Salida'] = df.apply(calc_dias, axis=1)

        # 7. Agrupar final
        df_agrupado = df.groupby(['Producto']).agg({
            'quantity': 'sum',
            'Valor': 'sum',
            'Dias_Sin_Salida': 'min', 
            'Ubicacion': lambda x: ", ".join(sorted(set(str(v) for v in x if v)))
        }).reset_index()
        
        df_huesos = df_agrupado.sort_values('Dias_Sin_Salida', ascending=False)
        
        return df_huesos, f"Filtro: {', '.join(nombres_bodegas)} (Solo Almacenables)"

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
    if os.path.exists("metas.xlsx"):
        df = pd.read_excel("metas.xlsx")
        df['Mes'] = pd.to_datetime(df['Mes'])
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})

# --- 5. INTERFAZ ---
st.title("🚀 Monitor Comercial ALROTEK v9.2")

with st.sidebar:
    logo_path = "logo.png"
    if os.path.exists(logo_path): st.image(logo_path, use_container_width=True)
    else: st.markdown("## 🏢 ALROTEK")
    
    st.divider()
    st.header("⚙️ Configuración Global")
    
    anios_posibles = list(range(datetime.now().year, 2020, -1))
    anio_global = st.selectbox("Año Fiscal:", anios_posibles, index=0)
    
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
        anio_ant = anio_global - 1
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_global]
        df_ant_data = df_main[df_main['invoice_date'].dt.year == anio_ant]
        
        venta = df_anio['Venta_Neta'].sum()
        venta_ant_total = df_ant_data['Venta_Neta'].sum()
        delta_anual = ((venta - venta_ant_total) / venta_ant_total * 100) if venta_ant_total > 0 else 0
        
        metas_filtradas = df_metas[df_metas['Anio'] == anio_global]
        meta = metas_filtradas['Meta'].sum()
        cumplimiento = (venta/meta*100) if meta > 0 else 0
        
        cant_facturas = df_anio['name'].nunique()
        ticket_promedio = (venta / cant_facturas) if cant_facturas > 0 else 0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: card_kpi("Venta Total", venta, "border-green", f"{delta_anual:.1f}% vs {anio_ant}", "💰")
        with k2: card_kpi("Meta Anual", meta, "border-gray", f"Falta: {100-cumplimiento:.1f}%", "🎯")
        with k3: card_kpi("Cumplimiento", f"{cumplimiento:.1f}%", "border-blue", "Sobre Objetivo", "📊")
        with k4: card_kpi("Ticket Promedio", ticket_promedio, "border-orange", f"{cant_facturas} Operaciones", "🧾")
        
        st.divider()
        
        # --- GRAFICOS RESTAURADOS (V9.2) ---
        col_top_graf, col_top_rank = st.columns([2, 1])
        
        with col_top_graf:
            st.markdown("### 📅 Tendencia vs Meta")
            v_mes_act = df_anio.groupby('Mes_Num')['Venta_Neta'].sum().reset_index()
            v_mes_act.columns = ['Mes_Num', 'Venta_Actual']
            v_metas = metas_filtradas.groupby('Mes_Num')['Meta'].sum().reset_index()
            df_chart = pd.DataFrame({'Mes_Num': range(1, 13)})
            df_chart = pd.merge(df_chart, v_mes_act, on='Mes_Num', how='left').fillna(0)
            df_chart = pd.merge(df_chart, v_metas, on='Mes_Num', how='left').fillna(0)
            nombres_meses = {1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic'}
            df_chart['Mes'] = df_chart['Mes_Num'].map(nombres_meses)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_chart['Mes'], y=df_chart['Venta_Actual'], name='Real', marker_color='#27ae60'))
            fig.add_trace(go.Scatter(x=df_chart['Mes'], y=df_chart['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
            fig.update_layout(template="plotly_white", height=350, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)
            
        with col_top_rank:
            st.markdown("### 🏆 Top Vendedores")
            rank = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index().sort_values('Venta_Neta', ascending=True).tail(8)
            fig_v = px.bar(rank, x='Venta_Neta', y='Vendedor', orientation='h', text_auto='.2s', color_discrete_sequence=['#2980b9'])
            fig_v.update_layout(template="plotly_white", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_v, use_container_width=True)
            
        # --- NUEVA FILA DE GRAFICOS (RESTORED) ---
        if not df_prod.empty:
            st.divider()
            col_mix1, col_mix2 = st.columns([1, 2])
            
            # Preparar datos del Plan
            df_lineas = df_prod[df_prod['date'].dt.year == anio_global].copy()
            mapa_planes = {}
            if not df_analitica.empty:
                mapa_planes = dict(zip(df_analitica['id_cuenta_analitica'].astype(str), df_analitica['Plan_Nombre']))
            
            def clasificar_plan(dist):
                if not dist: return "Sin Analítica"
                try:
                    d = dist if isinstance(dist, dict) else ast.literal_eval(str(dist))
                    for k in d.keys():
                        plan = mapa_planes.get(str(k))
                        if plan: return plan
                except: pass
                return "Otros"

            df_lineas['Plan'] = df_lineas['analytic_distribution'].apply(clasificar_plan)
            
            with col_mix1:
                st.markdown("### 🍰 Mix de Negocio (Planes)")
                ventas_plan = df_lineas.groupby('Plan')['Venta_Neta'].sum().reset_index()
                fig_pie = px.pie(ventas_plan, values='Venta_Neta', names='Plan', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_pie.update_layout(height=350, margin=dict(t=20,b=0,l=0,r=0))
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col_mix2:
                st.markdown("### 📶 Evolución por Línea de Negocio")
                df_lineas['Mes_Nombre'] = df_lineas['date'].dt.strftime('%m-%b')
                df_lineas['Mes_Num'] = df_lineas['date'].dt.month
                ventas_mes_plan = df_lineas.groupby(['Mes_Num', 'Mes_Nombre', 'Plan'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                fig_stack = px.bar(ventas_mes_plan, x='Mes_Nombre', y='Venta_Neta', color='Plan', title="", color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_stack.update_layout(height=350, margin=dict(t=20,b=0,l=0,r=0))
                st.plotly_chart(fig_stack, use_container_width=True)

# === PESTAÑA 2: PRODUCTOS ===
with tab_prod:
    if not df_prod.empty and not df_cat.empty:
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_global].copy()
        df_p_anio = pd.merge(df_p_anio, df_cat[['ID_Producto', 'Tipo', 'Referencia']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]
        
        col_down_p, _ = st.columns([1, 4])
        with col_down_p:
            df_export_prod = df_p_anio.groupby(['Referencia', 'Producto', 'Tipo'])[['quantity', 'Venta_Neta']].sum().reset_index()
            excel_prod = convert_df_to_excel(df_export_prod)
            st.download_button("📥 Descargar Excel", data=excel_prod, file_name=f"Productos_{anio_global}.xlsx")
            
        c1, c2 = st.columns([1, 2])
        with c1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(height=350, title="Mix de Venta")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.markdown(f"**Top 10 Productos ({anio_global})**")
            top_prod = df_p_anio.groupby('Producto')[['Venta_Neta']].sum().reset_index().sort_values('Venta_Neta', ascending=False).head(10).sort_values('Venta_Neta', ascending=True)
            fig_bar = px.bar(top_prod, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s', color='Venta_Neta', color_continuous_scale='Viridis')
            fig_bar.update_layout(height=350)
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
            
            total_ventas = 0; total_instalacion = 0; total_suministros = 0; total_wip = 0; total_provision = 0; total_ajustes = 0; total_costo_retail = 0; total_otros = 0

            if not df_filtered.empty:
                total_ventas = abs(df_filtered[df_filtered['Clasificacion'] == 'Venta']['Monto_Neto'].sum())
                total_instalacion = abs(df_filtered[df_filtered['Clasificacion'] == 'Instalación']['Monto_Neto'].sum())
                total_suministros = abs(df_filtered[df_filtered['Clasificacion'] == 'Suministros']['Monto_Neto'].sum())
                total_wip = abs(df_filtered[df_filtered['Clasificacion'] == 'WIP']['Monto_Neto'].sum())
                total_provision = abs(df_filtered[df_filtered['Clasificacion'] == 'Provisión']['Monto_Neto'].sum())
                total_ajustes = df_filtered[df_filtered['Clasificacion'] == 'Ajustes Inv']['Monto_Neto'].sum()
                total_costo_retail = abs(df_filtered[df_filtered['Clasificacion'] == 'Costo Retail']['Monto_Neto'].sum())
                df_otros_filtrado = df_filtered[df_filtered['Clasificacion'] == 'Otros Gastos']
                total_otros = abs(df_otros_filtrado['Monto_Neto'].sum())

            df_horas_detalle = cargar_detalle_horas_mes(ids_seleccionados)
            total_horas_ajustado = df_horas_detalle['Costo'].sum() if not df_horas_detalle.empty else 0
            
            df_stock_sitio, status_stock, bodegas_encontradas = cargar_inventario_ubicacion_proyecto_v4(ids_seleccionados, cuentas_sel_nombres)
            total_stock_sitio = df_stock_sitio['Valor_Total'].sum() if not df_stock_sitio.empty else 0
            
            df_compras = cargar_compras_pendientes_v7_json_scanner(ids_seleccionados, tc_usd)
            total_compras_pendientes = df_compras['Monto_Pendiente'].sum() if not df_compras.empty else 0
            
            df_fact_estimada = cargar_facturacion_estimada_v2(ids_projects, tc_usd)
            total_fact_pendiente = df_fact_estimada['Monto_CRC'].sum() if not df_fact_estimada.empty else 0
            
            txt_bodegas = "Sin ubicación"
            if status_stock == "OK" or status_stock == "NO_STOCK":
                txt_bodegas = f"Bodegas: {len(bodegas_encontradas)}"
            
            k1, k2, k3, k4 = st.columns(4)
            with k1: card_kpi("Ventas (Acum)", total_ventas, "border-green", "Ingresos Reales", "💰")
            with k2: card_kpi("Instalación", total_instalacion, "border-blue", "Costo MO Directa", "👷")
            with k3: card_kpi("Suministros", total_suministros, "border-light-orange", "Materiales", "🧱")
            with k4: card_kpi("WIP Acumulado", total_wip, "border-yellow", "Trabajo en Proceso", "🚧")
            
            k5, k6, k7, k8 = st.columns(4)
            with k5: card_kpi("Provisiones", total_provision, "border-red", "Gastos Futuros", "📉")
            with k6: card_kpi("Ajustes Inv.", total_ajustes, "border-gray", "Mermas/Sobrantes", "⚖️")
            with k7: card_kpi("Costo Retail", total_costo_retail, "border-orange", "Costo Venta Directa", "📦") 
            with k8: card_kpi("Otros Gastos", total_otros, "border-gray", "Ctas. Clase 6", "📄")
            
            k9, k10, k11, k12 = st.columns(4)
            with k9: card_kpi("Inventario Sitio", total_stock_sitio, "border-purple", txt_bodegas, "🏭")
            with k10: card_kpi("Compras Pendientes", total_compras_pendientes, "border-teal", "Ordenes Abiertas", "🚛")
            with k11: card_kpi("Nómina (Mes)", total_horas_ajustado, "border-blue", "Burn Rate Mensual", "🔥")
            with k12: card_kpi("Fact. Pendiente", total_fact_pendiente, "border-cyan", "Proyección", "🔮")
            
            st.divider()
            
            cg1, cg2 = st.columns([1, 1])
            with cg1:
                st.markdown("##### 📉 Estructura de Costos")
                labels = ['Instalación', 'Suministros', 'WIP', 'Provisiones', 'Otros', 'Nómina Mes']
                values = [total_instalacion, total_suministros, total_wip, total_provision, total_otros, total_horas_ajustado]
                fig_costos = px.pie(names=labels, values=values, hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
                fig_costos.update_layout(height=300, margin=dict(t=0,b=0,l=0,r=0))
                st.plotly_chart(fig_costos, use_container_width=True)
            
            with cg2:
                st.markdown("##### 📦 Detalle Inventario")
                if not df_stock_sitio.empty:
                    st.dataframe(df_stock_sitio[['pname', 'quantity', 'Valor_Total']], hide_index=True, use_container_width=True)
                else: st.info("No hay inventario en sitio.")

            with st.expander("📋 Ver Detalle de Compras y Facturación Pendiente"):
                t1, t2 = st.tabs(["Compras (OC)", "Facturación (Hitos)"])
                with t1:
                    if not df_compras.empty: st.dataframe(df_compras, use_container_width=True)
                    else: st.caption("Sin compras pendientes.")
                with t2:
                    if not df_fact_estimada.empty: st.dataframe(df_fact_estimada, use_container_width=True)
                    else: st.caption("Sin facturación pendiente.")

# === PESTAÑA 4: INVENTARIO (BAJA ROTACIÓN) ===
with tab_inv:
    with st.spinner("Calculando rotación..."):
        df_huesos, msg_status = cargar_inventario_baja_rotacion()
    
    col_header, col_filter = st.columns([3, 1])
    with col_header:
        st.subheader("📦 Análisis de Baja Rotación (Huesos)")
        st.caption(msg_status)
    with col_filter:
        dias_min = st.number_input("Días sin Salidas >", min_value=0, value=365, step=30)
    
    if not df_huesos.empty:
        df_show = df_huesos[df_huesos['Dias_Sin_Salida'] >= dias_min]
        total_atrapado = df_show['Valor'].sum()
        items_totales = len(df_huesos) 
        items_hueso = len(df_show)
        
        m1, m2, m3 = st.columns(3)
        card_kpi(f"Capital Estancado (>{dias_min}d)", total_atrapado, "border-red", "Dinero Inmovilizado", "💸")
        card_kpi("Total Items en Bodega", items_totales, "border-blue", "SKUs con existencia", "📦")
        card_kpi("Items Hueso", items_hueso, "border-orange", "Requieren Acción", "⚠️")
        
        st.divider()
        
        st.dataframe(
            df_show[['Producto', 'Ubicacion', 'quantity', 'Dias_Sin_Salida', 'Valor']],
            column_config={
                "Valor": st.column_config.NumberColumn(format="₡ %.2f"),
                "quantity": st.column_config.NumberColumn("Cant."),
                "Dias_Sin_Salida": st.column_config.ProgressColumn("Días Sin Salida", min_value=0, max_value=720, format="%d días"),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No se encontró inventario bajo los criterios actuales.")

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    with st.spinner('Analizando deudas...'):
        df_cx = cargar_cartera()
    if not df_cx.empty:
        total_deuda = df_cx['amount_residual'].sum()
        total_vencido = df_cx[df_cx['Dias_Vencido'] > 0]['amount_residual'].sum()
        
        k1, k2 = st.columns(2)
        with k1: card_kpi("Total por Cobrar", total_deuda, "border-blue", "Cartera Total", "💰")
        with k2: card_kpi("Vencido", total_vencido, "border-red", "> 0 Días", "🚨")
        
        st.divider()
        
        col_table, col_chart = st.columns([2, 1])
        with col_chart:
            df_buckets = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            fig_cx = px.pie(df_buckets, values='amount_residual', names='Antiguedad', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            fig_cx.update_layout(height=350, margin=dict(t=0,b=0,l=0,r=0))
            st.plotly_chart(fig_cx, use_container_width=True)
            
        with col_table:
            st.dataframe(
                df_cx[['Cliente', 'invoice_date_due', 'amount_residual', 'Antiguedad']].sort_values('amount_residual', ascending=False),
                column_config={
                    "amount_residual": st.column_config.NumberColumn("Deuda", format="₡ %.2f"),
                    "invoice_date_due": st.column_config.DateColumn("Vencimiento")
                },
                use_container_width=True,
                hide_index=True
            )
    else:
        st.success("¡Felicidades! No hay cuentas por cobrar pendientes.")

# === PESTAÑA 6: SEGMENTACIÓN CLIENTES ===
with tab_cli:
    if not df_main.empty:
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_global]
        
        c1, c2, c3 = st.columns(3)
        with c1:
            ventas_prov = df_c_anio.groupby('Provincia')['Venta_Neta'].sum().reset_index()
            fig = px.pie(ventas_prov, values='Venta_Neta', names='Provincia', title="Por Provincia")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            ventas_cat = df_c_anio.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index()
            fig = px.pie(ventas_cat, values='Venta_Neta', names='Categoria_Cliente', title="Por Categoría")
            st.plotly_chart(fig, use_container_width=True)
        with c3:
            top_cli = df_c_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).reset_index()
            st.dataframe(top_cli, column_config={"Venta_Neta": st.column_config.NumberColumn(format="₡ %.2f")}, hide_index=True)

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        df_v_anio = df_main[df_main['invoice_date'].dt.year == anio_global]
        rank = df_v_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index().sort_values('Venta_Neta', ascending=False)
        
        st.subheader(f"Ranking Comercial {anio_global}")
        fig = px.bar(rank, x='Venta_Neta', y='Vendedor', orientation='h', text_auto='.2s', color='Venta_Neta', color_continuous_scale='Blues')
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

# === PESTAÑA 8: RADIOGRAFÍA CLIENTE ===
with tab_det:
    if not df_main.empty:
        cliente_sel = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()))
        if cliente_sel:
            df_cli = df_main[df_main['Cliente'] == cliente_sel]
            total = df_cli['Venta_Neta'].sum()
            card_kpi("Venta Histórica", total, "border-green", "Total Facturado", "🏛️")
            st.dataframe(df_cli[['invoice_date', 'name', 'Venta_Neta']].sort_values('invoice_date', ascending=False), use_container_width=True)
