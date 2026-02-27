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
            
            # --- NUEVO: DOLARIZACIÓN EXACTA ---
            usd_curr = models.execute_kw(DB, uid, PASSWORD, 'res.currency', 'search_read', [[['name', '=', 'USD']]], {'fields': ['id']})
            if usd_curr:
                usd_id = usd_curr[0]['id']
                domain_rates = [['currency_id', '=', usd_id], ['name', '>=', '2021-01-01'], ['company_id', '=', COMPANY_ID]]
                rates = models.execute_kw(DB, uid, PASSWORD, 'res.currency.rate', 'search_read', [domain_rates], {'fields': ['name', 'rate']})
                if rates:
                    df_rates = pd.DataFrame(rates)
                    df_rates['name'] = pd.to_datetime(df_rates['name'])
                    df_rates = df_rates.rename(columns={'name': 'date_rate'})
                    df_rates = df_rates.sort_values('date_rate')
                    # Hacemos merge_asof para buscar la tasa vigente en o antes de la fecha de la factura
                    df = df.sort_values('invoice_date')
                    df = pd.merge_asof(df, df_rates[['date_rate', 'rate']], left_on='invoice_date', right_on='date_rate', direction='backward')
                    # La tasa base suele ser 1/rate o el rate mismo dependiendo de cómo esté configurado Odoo respecto a CRC.
                    # En CR normalmente rate (company_rate) para USD es = tc_usd. (Por ej: 1 USD = 515 CRC -> rate es 0.00194, o al revés).
                    # De acuerdo a debug_rates.py el rate ronda los 0.0019 - 0.0021. Eso significa que es 1 / TC.
                    # Por tanto, USD = CRC * rate
                    df['usd_rate'] = df['rate'].fillna(0.0019)  # Fallback
                    df['Venta_Neta_USD'] = df['Venta_Neta'] * df['usd_rate']
                else:
                    df['Venta_Neta_USD'] = df['Venta_Neta'] / 515.0
            else:
                df['Venta_Neta_USD'] = df['Venta_Neta'] / 515.0
                
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
        anio_inicio = datetime.now().year - 3
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
def cargar_historial_inventario_proyecto(ids_an, names_an, project_id=None):
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

        # 2. Búsqueda por Cuenta Analítica o Nombre -> Poner en ids_proy
        ids_proy = []
        if ids_an: 
            try: 
                ids_proy += models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['analytic_account_id', 'in', [int(x) for x in ids_an if x]]]])
            except: pass
            
        if names_an:
            try:
                ids_proy += models.execute_kw(DB, uid, PASSWORD, 'project.project', 'search', [[['name', 'in', names_an]]])
            except: pass
        
        ids_proy = list(set(ids_proy))
            
        # Buscar ubicaciones usando los IDs de PROYECTO encontrados
        if ids_proy:
             ids_loc += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['x_studio_field_qCgKk', 'in', ids_proy]]])
             
        # 3. Búsqueda por Nombre (Legacy / Fallback)
        if names_an and not ids_loc:
            for n in names_an:
                if len(n)>4: ids_loc += models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['name', 'ilike', n.split(' ')[0]]]])
        
        ids_loc = list(set(ids_loc))
        if not ids_loc: return pd.DataFrame(), "NO_BODEGA"
        
        # 4. Obtener pickings desde Órdenes de Venta ligadas a la Cuenta Analítica del Proyecto
        # Esto soluciona el caso donde el material sale de "BP/Stock" hacia el cliente pero pertenece al proyecto.
        ids_pickings_so = []
        if ids_an:
            # Buscar SOs de este proyecto
            sos = models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'search_read', [[['analytic_account_id', 'in', ids_an]]], {'fields': ['picking_ids']})
            for so in sos:
                if so.get('picking_ids'):
                    ids_pickings_so.extend(so['picking_ids'])
                    
        # 5. Combinar movimientos (Físicos de la ubicación + Despachos de las SOs)
        domain_moves_loc = [
            ['state', '=', 'done'],
            '|',
            ['location_id', 'child_of', ids_loc],
            ['location_dest_id', 'child_of', ids_loc],
            ['company_id', '=', COMPANY_ID]
        ]
        ids_moves_loc = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'search', [domain_moves_loc])
        
        ids_moves_so = []
        if ids_pickings_so:
            domain_moves_so = [['state', '=', 'done'], ['picking_id', 'in', ids_pickings_so], ['company_id', '=', COMPANY_ID]]
            ids_moves_so = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'search', [domain_moves_so])
            
        ids_moves_all = list(set(ids_moves_loc + ids_moves_so))
        
        if not ids_moves_all: return pd.DataFrame(), "NO_MOVES"
        
        # 6. Leer los campos necesarios
        fields = ['product_id', 'product_uom_qty', 'quantity_done', 'location_id', 'location_dest_id', 'date']
        moves_data = models.execute_kw(DB, uid, PASSWORD, 'stock.move', 'read', [ids_moves_all], {'fields': fields})
        
        df_moves = pd.DataFrame(moves_data)
        if df_moves.empty: return pd.DataFrame(), "ERROR"
        
        # Marcar cuáles movimientos entraron por ser de SO vs de Ubicación para el cálculo de Entregas
        # Si un movimiento NO toca child_locs (ej: sale directo de BP/Stock al Customer) lo aceptamos para Entregas
        df_moves['from_so'] = df_moves['id'].isin(ids_moves_so)
        
        # 5. Filtrar Movimientos: Ensambles (Producción) y Entregas (Cliente)
        # Identificaremos si la ubicación origen o destino es de tipo "production" o "customer"
        
        # Recolectar todos los IDs de ubicaciones involucradas
        all_locs = set()
        for x in df_moves['location_id'].dropna():
            if isinstance(x, list) and x: all_locs.add(x[0])
        for x in df_moves['location_dest_id'].dropna():
            if isinstance(x, list) and x: all_locs.add(x[0])
            
        # Consultar su "usage" y "complete_name"
        loc_info = {}
        if all_locs:
            locs_data = models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'read', [list(all_locs)], {'fields': ['usage', 'complete_name']})
            for l in locs_data:
                loc_info[l['id']] = {
                    'usage': l.get('usage', 'internal'),
                    'name': l.get('complete_name', '')
                }
        
        # Filtrar el dataframe para quedarnos SOLAMENTE con los movimientos que interactúan con Producción o Clientes (Estrictamente "Partner Locations/Customers")
        def is_production_move(row):
            src_id = row['location_id'][0] if isinstance(row['location_id'], list) else None
            dst_id = row['location_dest_id'][0] if isinstance(row['location_dest_id'], list) else None
            return loc_info.get(src_id, {}).get('usage') == 'production' or loc_info.get(dst_id, {}).get('usage') == 'production'

        def is_customer_move(row):
            src_id = row['location_id'][0] if isinstance(row['location_id'], list) else None
            dst_id = row['location_dest_id'][0] if isinstance(row['location_dest_id'], list) else None
            
            src_name = loc_info.get(src_id, {}).get('name', '')
            dst_name = loc_info.get(dst_id, {}).get('name', '')
            
            return 'Partner Locations/Customers' in str(src_name) or 'Partner Locations/Customers' in str(dst_name)
            
        def is_post_move(row):
            src_id = row['location_id'][0] if isinstance(row['location_id'], list) else None
            dst_id = row['location_dest_id'][0] if isinstance(row['location_dest_id'], list) else None
            
            src_name = loc_info.get(src_id, {}).get('name', '')
            dst_name = loc_info.get(dst_id, {}).get('name', '')
            
            return 'PROJ/POST/' in str(src_name) or 'PROJ/POST/' in str(dst_name)
            
        df_prod = df_moves[df_moves.apply(is_production_move, axis=1)].copy()
        df_cust = df_moves[df_moves.apply(is_customer_move, axis=1)].copy()
        df_post = df_moves[df_moves.apply(is_post_move, axis=1)].copy()
        
        # Obtener todas las ubicaciones anidadas del proyecto para mayor seguridad
        child_locs = set(models.execute_kw(DB, uid, PASSWORD, 'stock.location', 'search', [[['id', 'child_of', ids_loc]]]))
        
        def is_in(row):
            dest_id = row['location_dest_id'][0] if row['location_dest_id'] else 0
            # Si el destino es el cliente y el movimiento vino por la SO, para el cliente esto es OUT (Entrega), no un IN al proyecto.
            # IN para el proyecto es si el destino físico es la bodega del proyecto.
            return dest_id in child_locs
            
        def is_out(row):
            src_id = row['location_id'][0] if row['location_id'] else 0
            return src_id in child_locs
            
        # 8. Calcular Cantidades - Producción
        grp_prod = pd.DataFrame()
        if not df_prod.empty:
            df_prod['is_in_move'] = df_prod.apply(is_in, axis=1)
            df_prod['is_out_move'] = df_prod.apply(is_out, axis=1)
            df_prod['qty'] = df_prod['quantity_done'].fillna(df_prod['product_uom_qty']).fillna(0)
            
            # Mapeo a terminología MRP:
            df_prod['Ensamblado_OUT'] = df_prod.apply(lambda r: r['qty'] if r['is_out_move'] and not r['is_in_move'] else 0, axis=1)
            df_prod['Desensamblado_IN'] = df_prod.apply(lambda r: r['qty'] if r['is_in_move'] and not r['is_out_move'] else 0, axis=1)
            
            df_prod['pid'] = df_prod['product_id'].apply(lambda x: x[0] if x else 0)
            df_prod['Producto'] = df_prod['product_id'].apply(lambda x: x[1] if x else 'Desc')
            
            grp_prod = df_prod.groupby(['pid', 'Producto']).agg({'Ensamblado_OUT':'sum', 'Desensamblado_IN':'sum'}).reset_index()
            grp_prod['Neto_Ensamblado'] = grp_prod['Ensamblado_OUT'] - grp_prod['Desensamblado_IN']
            grp_prod = grp_prod.sort_values('Neto_Ensamblado', ascending=False)
            grp_prod = grp_prod[(grp_prod['Ensamblado_OUT'] != 0) | (grp_prod['Desensamblado_IN'] != 0)]

        # 9. Calcular Cantidades - Clientes
        grp_cust = pd.DataFrame()
        if not df_cust.empty:
            df_cust['qty'] = df_cust['quantity_done'].fillna(df_cust['product_uom_qty']).fillna(0)
            
            # Mapeo a terminología Cliente:
            # Entregado = El destino es "Partner Locations/Customers" (ya el df_cust solo tiene movimientos de Customers, así que validamos si el destino es el Customer).
            def cust_entregado(r):
                dst_id = r['location_dest_id'][0] if r['location_dest_id'] else None
                return r['qty'] if 'Partner Locations/Customers' in str(loc_info.get(dst_id, {}).get('name', '')) else 0
                
            def cust_devuelto(r):
                src_id = r['location_id'][0] if r['location_id'] else None
                return r['qty'] if 'Partner Locations/Customers' in str(loc_info.get(src_id, {}).get('name', '')) else 0
            
            df_cust['Entregado_OUT'] = df_cust.apply(cust_entregado, axis=1)
            df_cust['Devuelto_IN'] = df_cust.apply(cust_devuelto, axis=1)
            
            df_cust['pid'] = df_cust['product_id'].apply(lambda x: x[0] if x else 0)
            df_cust['Producto'] = df_cust['product_id'].apply(lambda x: x[1] if x else 'Desc')
            
            grp_cust = df_cust.groupby(['pid', 'Producto']).agg({'Entregado_OUT':'sum', 'Devuelto_IN':'sum'}).reset_index()
            grp_cust['Neto_Entregado'] = grp_cust['Entregado_OUT'] - grp_cust['Devuelto_IN']
            grp_cust = grp_cust.sort_values('Neto_Entregado', ascending=False)
            grp_cust = grp_cust[(grp_cust['Entregado_OUT'] != 0) | (grp_cust['Devuelto_IN'] != 0)]

        # 10. Calcular Cantidades - Ajustes Posteriores (PROJ/POST/)
        grp_post = pd.DataFrame()
        if not df_post.empty:
            df_post['is_in_move'] = df_post.apply(is_in, axis=1)
            df_post['is_out_move'] = df_post.apply(is_out, axis=1)
            df_post['qty'] = df_post['quantity_done'].fillna(df_post['product_uom_qty']).fillna(0)
            
            # Mapeo a terminología Post:
            df_post['Ajuste_OUT'] = df_post.apply(lambda r: r['qty'] if r['is_out_move'] and not r['is_in_move'] else 0, axis=1)
            df_post['Ajuste_IN'] = df_post.apply(lambda r: r['qty'] if r['is_in_move'] and not r['is_out_move'] else 0, axis=1)
            
            df_post['pid'] = df_post['product_id'].apply(lambda x: x[0] if x else 0)
            df_post['Producto'] = df_post['product_id'].apply(lambda x: x[1] if x else 'Desc')
            
            grp_post = df_post.groupby(['pid', 'Producto']).agg({'Ajuste_OUT':'sum', 'Ajuste_IN':'sum'}).reset_index()
            grp_post['Neto_Ajuste'] = grp_post['Ajuste_OUT'] - grp_post['Ajuste_IN']
            grp_post = grp_post.sort_values('Neto_Ajuste', ascending=False)
            grp_post = grp_post[(grp_post['Ajuste_OUT'] != 0) | (grp_post['Ajuste_IN'] != 0)]

        status_msg = "OK"
        if grp_prod.empty and grp_cust.empty and grp_post.empty:
            status_msg = "NO_MOVES"
            
        return grp_prod, grp_cust, grp_post, status_msg
    except Exception as e: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), str(e)

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
        df['Cantidad'] = df['qty_pending']
        df['Producto'] = df['name']
        df = df.drop(columns=['order_id', 'partner_id', 'analytic_distribution', 'currency_id', 'name'], errors='ignore')
        return df[['OC', 'Proveedor', 'Producto', 'Cantidad', 'Monto_Pendiente']]
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

