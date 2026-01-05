# services.py
import streamlit as st
import pandas as pd
import xmlrpc.client
from datetime import datetime, timedelta
import ast
import os
import config

# --- CREDENCIALES ---
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    COMPANY_ID = st.secrets["odoo"]["company_id"]
except Exception:
    st.error("❌ Error: Credenciales no encontradas en .streamlit/secrets.toml")
    st.stop()

# --- FUNCIONES DE CARGA DE DATOS ---

@st.cache_data(ttl=900) 
def cargar_datos_generales():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        if not uid: return None
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio = [['move_type', 'in', ['out_invoice', 'out_refund']], ['state', '=', 'posted'], ['invoice_date', '>=', '2021-01-01'], ['company_id', '=', COMPANY_ID]]
        campos = ['name', 'invoice_date', 'invoice_date_due', 'amount_untaxed_signed', 'partner_id', 'invoice_user_id']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'read', [ids], {'fields': campos})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['invoice_date_due'] = pd.to_datetime(df['invoice_date_due'])
            df['Dias_Credito'] = (df['invoice_date_due'] - df['invoice_date']).dt.days
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
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': ['name', 'qty_available', 'standard_price', 'detailed_type', 'default_code', 'brand_alrotek_id']})
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
            
            # Procesar Marca (brand_alrotek_id)
            def extract_brand(val):
                if isinstance(val, list) and len(val) > 1:
                    return val[1]
                return "Sin Marca"
            
            df['Marca'] = df['brand_alrotek_id'].apply(extract_brand) if 'brand_alrotek_id' in df.columns else "Sin Marca"
            
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
        ids = list(set(config.TODOS_LOS_IDS + models.execute_kw(DB, uid, PASSWORD, 'account.account', 'search', [[['code', '=like', '6%']]])))
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
                if id_acc in config.IDS_INGRESOS: return "Venta"
                if id_acc == config.ID_WIP: return "WIP"
                if id_acc == config.ID_PROVISION_PROY: return "Provisión"
                if id_acc == config.ID_COSTO_INSTALACION: return "Instalación"
                if id_acc == config.ID_SUMINISTROS_PROY: return "Suministros"
                if id_acc == config.ID_AJUSTES_INV: return "Ajustes Inv"
                if id_acc == config.ID_COSTO_RETAIL: return "Costo Retail"
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
def cargar_inventario_ubicacion_proyecto_v4(ids_an, names_an, project_id=None):
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        ids_loc = []
        
        # 1. Búsqueda DIRECTA por ID de Proyecto (Prioridad Alta)
        if project_id:
            try:
                locs_by_proj = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', '=', project_id]]])
                if locs_by_proj: ids_loc += locs_by_proj
            except: pass

        # 2. Búsqueda por Cuenta Analítica
        ids_proy = []
        if ids_an: 
            try: 
                ids_proy += models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', [int(x) for x in ids_an if x]]]])
            except: pass
            
            # 3. Búsqueda por Nombre de Proyecto (Siempre ejecutar para mayor robustez)
        if names_an:
            try:
                # Buscar también por nombre para asegurar coincidencia
                ids_proy += models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['name', 'in', names_an]]])
            except: pass
        
        # Eliminar duplicados de Proyectos encontrados
        ids_proy = list(set(ids_proy))
            
        # Buscar ubicaciones usando los IDs de PROYECTO encontrados
        if ids_proy:
             ids_loc += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', 'in', ids_proy]]])

            
        # 3. Búsqueda por Nombre (Legacy / Fallback)
        if names_an and not ids_loc:
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
    # URL RAW de GitHub del archivo metas.csv
    GITHUB_CSV_URL = "https://raw.githubusercontent.com/jasonsrm12592/dashboard-artk/main/metas.csv"
    
    try:
        # Intentar leer desde GitHub
        df = pd.read_csv(GITHUB_CSV_URL)
        df['Mes'] = pd.to_datetime(df['Mes'])
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    except Exception as e:
        # Si falla (sin internet, etc), intentar leer archivo local
        if os.path.exists("metas.csv"):
            df = pd.read_csv("metas.csv")
            df['Mes'] = pd.to_datetime(df['Mes'])
            df['Mes_Num'] = df['Mes'].dt.month
            df['Anio'] = df['Mes'].dt.year
            return df
            
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})
