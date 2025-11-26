import streamlit as st
import pandas as pd
import xmlrpc.client
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import io
import os

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Alrotek Sales Monitor", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .block-container {padding-top: 1rem; padding-bottom: 1rem;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- 2. CREDENCIALES & CUENTAS (IDs EXACTOS) ---
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    COMPANY_ID = st.secrets["odoo"]["company_id"]
    
    # === CONFIGURACIÓN CONTABLE (IDs de la Imagen) ===
    
    # 1. INGRESOS (Ventas, Servicios, Devoluciones, Descuentos)
    # Incluimos 77 y 78 para que resten automáticamente al hacer (Crédito - Débito)
    IDS_INGRESOS = [
        68, 398, 66, 69, 401, 403, 404, 405, 406, 407, 408, 409, 410, # Ventas
        77, 78 # Devoluciones y Descuentos (Restan)
    ]
    
    # 2. COSTOS (Los que definimos antes)
    ID_COSTO_RETAIL = 76            # 0.511 Costo mercadería
    IDS_COSTO_PROY = [399, 400, 402, 395] # Costos de Servicios/Instalación
    
    # 3. WIP
    ID_WIP = 503                    # 0.11531 WIP
    
    # Lista maestra para filtrar la consulta contable
    TODOS_LOS_IDS = IDS_INGRESOS + [ID_COSTO_RETAIL] + IDS_COSTO_PROY + [ID_WIP]
    
except Exception:
    st.error("❌ Error: No encuentro el archivo .streamlit/secrets.toml")
    st.stop()

# --- 3. FUNCIONES UTILITARIAS ---
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
    return output.getvalue()

# --- 4. FUNCIONES DE CARGA ---

@st.cache_data(ttl=900) 
def cargar_datos_generales():
    """Descarga FACTURAS (Operativo)"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        if not uid: return None
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        dominio = [
            ['move_type', 'in', ['out_invoice', 'out_refund']],
            ['state', '=', 'posted'],
            ['invoice_date', '>=', '2021-01-01'],
            ['company_id', '=', COMPANY_ID]
        ]
        
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
    except Exception as e:
        st.error(f"Error Odoo Facturas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_datos_clientes_extendido(ids_clientes):
    """Descarga ZONAS"""
    try:
        if not ids_clientes: return pd.DataFrame()
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        campos = ['state_id', 'x_studio_zona', 'x_studio_categoria_cliente']
        registros = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'read', [list(ids_clientes)], {'fields': campos})
        
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
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600) 
def cargar_detalle_productos():
    """Descarga LÍNEAS DE FACTURA"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        anio_inicio = datetime.now().year - 1
        dominio = [
            ['parent_state', '=', 'posted'],
            ['date', '>=', f'{anio_inicio}-01-01'], 
            ['company_id', '=', COMPANY_ID],
            ['display_type', '=', 'product'],
            ['move_id.move_type', 'in', ['out_invoice', 'out_refund']]
        ]
        campos = ['date', 'product_id', 'credit', 'debit', 'quantity', 'name', 'move_id']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['ID_Factura'] = df['move_id'].apply(lambda x: x[0] if x else 0)
            df['ID_Producto'] = df['product_id'].apply(lambda x: x[0] if x else 0)
            df['Producto'] = df['product_id'].apply(lambda x: x[1] if x else "Otros")
            df['Venta_Neta'] = df['credit'] - df['debit']
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario():
    """Descarga STOCK"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        try:
            ids_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
            kits_data = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'read', [ids_kits], {'fields': ['product_tmpl_id']})
            ids_templates_kit = [k['product_tmpl_id'][0] for k in kits_data if k['product_tmpl_id']]
        except:
            ids_templates_kit = []

        dominio = [['active', '=', True]]
        campos = ['name', 'qty_available', 'list_price', 'standard_price', 'detailed_type', 'create_date', 'product_tmpl_id', 'default_code']
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['create_date'] = pd.to_datetime(df['create_date'])
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo', 'default_code': 'Referencia'}, inplace=True)
            df['ID_Template'] = df['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
            if ids_templates_kit: df = df[~df['ID_Template'].isin(ids_templates_kit)]
            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_estructura_analitica():
    """Descarga PLANES y CUENTAS"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        dominio_todo = ['|', ['active', '=', True], ['active', '=', False]]
        ids_plans = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'search', [dominio_todo])
        plans = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.plan', 'read', [ids_plans], {'fields': ['name']})
        df_plans = pd.DataFrame(plans).rename(columns={'id': 'plan_id', 'name': 'Plan_Nombre'})
        ids_acc = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'search', [dominio_todo])
        accounts = models.execute_kw(DB, uid, PASSWORD, 'account.analytic.account', 'read', [ids_acc], {'fields': ['name', 'plan_id']})
        df_acc = pd.DataFrame(accounts)
        if not df_acc.empty and not df_plans.empty:
            df_acc['plan_id'] = df_acc['plan_id'].apply(lambda x: x[0] if x else 0)
            df_full = pd.merge(df_acc, df_plans, on='plan_id', how='left')
            df_full.rename(columns={'id': 'id_cuenta_analitica', 'name': 'Cuenta_Nombre'}, inplace=True)
            return df_full
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_pnl_contable(anio):
    """Descarga P&L REAL usando IDs de cuenta"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # FILTRO POR ID EXACTO (Mucho más seguro)
        dominio_pnl = [
            ['account_id', 'in', TODOS_LOS_IDS], # Solo las cuentas que nos interesan
            ['date', '>=', f'{anio}-01-01'],
            ['date', '<=', f'{anio}-12-31'],
            ['company_id', '=', COMPANY_ID],
            ['parent_state', '=', 'posted']
        ]
        
        campos = ['date', 'account_id', 'debit', 'credit', 'analytic_distribution', 'name']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio_pnl])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        
        if not df.empty:
            df['ID_Cuenta'] = df['account_id'].apply(lambda x: x[0] if x else 0)
            df['Nombre_Cuenta'] = df['account_id'].apply(lambda x: x[1] if x else "")
            
            # Monto Neto: (Crédito - Débito)
            # Ingresos = Crédito (+), Devoluciones = Débito (-) -> Resultado correcto
            df['Monto_Neto'] = df['credit'] - df['debit']
            
            # CLASIFICACIÓN EXACTA POR ID
            def clasificar(row):
                id_acc = row['ID_Cuenta']
                
                if id_acc in IDS_INGRESOS: return "Venta"
                if id_acc == ID_COSTO_RETAIL: return "Costo Retail"
                if id_acc in IDS_COSTO_PROY: return "Costo Proyecto"
                if id_acc == ID_WIP: return "WIP"
                return "Otro"
            
            df['Clasificacion'] = df.apply(clasificar, axis=1)
            
            def get_analytic_id(dist):
                if not dist: return None
                try: 
                    if isinstance(dist, dict): return int(list(dist.keys())[0])
                except: pass
                return None
            
            df['id_cuenta_analitica'] = df['analytic_distribution'].apply(get_analytic_id)
            
        return df

    except Exception as e:
        st.error(f"Error Contabilidad: {e}")
        return pd.DataFrame()

def cargar_metas():
    if os.path.exists("metas.xlsx"):
        df = pd.read_excel("metas.xlsx")
        df['Mes'] = pd.to_datetime(df['Mes'])
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})

# --- 5. INTERFAZ ---
st.title("🚀 Monitor Comercial ALROTEK")

tab_kpis, tab_prod, tab_renta, tab_inv, tab_cli, tab_vend, tab_det = st.tabs([
    "📊 Visión General", 
    "📦 Productos", 
    "📈 Rentabilidad P&L", 
    "🧟 Inventario", 
    "👥 Segmentación",
    "💼 Vendedores",
    "🔍 Radiografía"
])

with st.spinner('Sincronizando todo...'):
    df_main = cargar_datos_generales()
    df_prod = cargar_detalle_productos()
    df_cat = cargar_inventario()
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

            st.subheader(f"🎯 Desempeño vs Meta ({anio_sel})")
            colores = ['#27ae60' if r >= m else '#c0392b' for r, m in zip(df_chart['Venta_Actual'], df_chart['Meta'])]
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(x=df_chart['Mes_Nombre'], y=df_chart['Venta_Actual'], name='Venta Real', marker_color=colores, text=df_chart['Venta_Actual'].apply(lambda x: f'{x/1e6:.0f}' if x > 0 else ''), textposition='auto'))
            fig1.add_trace(go.Scatter(x=df_chart['Mes_Nombre'], y=df_chart['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
            fig1.update_layout(template="plotly_white", height=400, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig1, use_container_width=True)

            st.divider()

            st.subheader(f"📅 Comparativo: {anio_sel} vs {anio_ant}")
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_chart['Mes_Nombre'], y=df_chart['Venta_Anterior'], name=f'{anio_ant}', marker_color='#95a5a6', opacity=0.6))
            fig2.add_trace(go.Bar(x=df_chart['Mes_Nombre'], y=df_chart['Venta_Actual'], name=f'{anio_sel}', marker_color='#2980b9', text=df_chart['Venta_Actual'].apply(lambda x: f'{x/1e6:.0f}' if x > 0 else ''), textposition='auto'))
            fig2.update_layout(template="plotly_white", height=400, legend=dict(orientation="h", y=1.1), barmode='group')
            st.plotly_chart(fig2, use_container_width=True)
            
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

# === PESTAÑA 3: RENTABILIDAD P&L ===
with tab_renta:
    anio_r_sel = st.selectbox("Año Financiero", anios, key="renta_anio")
    
    with st.spinner('Cargando datos contables...'):
        df_pnl = cargar_pnl_contable(anio_r_sel)
    
    if not df_pnl.empty:
        if not df_analitica.empty:
            mapa_cuentas = dict(zip(df_analitica['id_cuenta_analitica'].astype(float), df_analitica['Plan_Nombre']))
            df_pnl['Plan_Negocio'] = df_pnl['id_cuenta_analitica'].map(mapa_cuentas).fillna("Sin Plan")
        else:
            df_pnl['Plan_Negocio'] = "Sin Analítica"

        # Clasificación
        def asignar_linea(row):
            plan = row['Plan_Negocio']
            clasif = row['Clasificacion']
            
            if clasif == 'Venta' and plan == 'Sin Plan': return 'Retail'
            if clasif == 'Costo Retail': return 'Retail'
            if plan != 'Sin Plan': return plan
            
            return 'Otros'

        df_pnl['Linea_Negocio'] = df_pnl.apply(asignar_linea, axis=1)

        # Agrupar P&L
        df_fin = df_pnl[df_pnl['Clasificacion'].isin(['Venta', 'Costo Retail', 'Costo Proyecto'])]
        
        resumen = df_fin.groupby(['Linea_Negocio', 'Clasificacion'])['Monto_Neto'].sum().unstack(fill_value=0)
        
        if 'Venta' not in resumen.columns: resumen['Venta'] = 0
        if 'Costo Retail' not in resumen.columns: resumen['Costo Retail'] = 0
        if 'Costo Proyecto' not in resumen.columns: resumen['Costo Proyecto'] = 0
        
        resumen['Costo_Total'] = (resumen['Costo Retail'] + resumen['Costo Proyecto']).abs()
        resumen['Margen_Bruto'] = resumen['Venta'] - resumen['Costo_Total']
        resumen['Margen %'] = (resumen['Margen_Bruto'] / resumen['Venta'] * 100).fillna(0)
        resumen = resumen.sort_values('Venta', ascending=False)

        st.subheader("📈 Estado de Resultados por Línea")
        
        c_r1, c_r2 = st.columns([2, 1])
        with c_r1:
            fig_mix = go.Figure()
            fig_mix.add_trace(go.Bar(x=resumen.index, y=resumen['Venta'], name='Venta', marker_color='#2980b9'))
            fig_mix.add_trace(go.Bar(x=resumen.index, y=resumen['Costo_Total'], name='Costo', marker_color='#e74c3c'))
            fig_mix.add_trace(go.Bar(x=resumen.index, y=resumen['Margen_Bruto'], name='Utilidad', marker_color='#27ae60'))
            fig_mix.update_layout(barmode='group', height=400)
            st.plotly_chart(fig_mix, use_container_width=True)
            
        with c_r2:
            fig_m = px.bar(resumen, x='Margen %', y=resumen.index, orientation='h', text_auto='.1f', color='Margen %', color_continuous_scale='RdYlGn')
            st.plotly_chart(fig_m, use_container_width=True)
            
        st.divider()
        
        # WIP
        st.subheader("🏗️ Control de Proyectos en Proceso (WIP)")
        df_wip = df_pnl[df_pnl['Clasificacion'] == 'WIP']
        if not df_wip.empty:
            total_wip = df_wip['Monto_Neto'].sum()
            st.metric("Saldo en WIP", f"₡ {total_wip:,.0f}")
            wip_det = df_wip.groupby('Linea_Negocio')['Monto_Neto'].sum().sort_values(ascending=False)
            st.bar_chart(wip_det)
        else:
            st.info("Sin saldo en WIP.")

# === PESTAÑA 4: INVENTARIO ===
with tab_inv:
    if not df_cat.empty:
        st.subheader("⚠️ Detección de Baja Rotación (Productos Hueso)")
        anio_hueso = anio_p_sel if 'anio_p_sel' in locals() else datetime.now().year
        
        df_stock_real = df_cat[df_cat['Stock'] > 0].copy()
        ids_vendidos = set(df_prod[df_prod['date'].dt.year == anio_hueso]['ID_Producto'].unique())
        df_zombies = df_stock_real[~df_stock_real['ID_Producto'].isin(ids_vendidos)].copy()
        df_zombies = df_zombies[df_zombies['create_date'].dt.year < anio_hueso]
        df_zombies = df_zombies[df_zombies['Tipo'] == 'Almacenable']
        
        df_zombies = df_zombies.sort_values('Valor_Inventario', ascending=False)
        total_atrapado = df_zombies['Valor_Inventario'].sum()
        
        col_down_z, _ = st.columns([1, 4])
        with col_down_z:
            excel_huesos = convert_df_to_excel(df_zombies[['Referencia', 'Producto', 'create_date', 'Stock', 'Costo', 'Valor_Inventario']])
            st.download_button("📥 Descargar Lista Huesos", data=excel_huesos, file_name=f"Productos_Hueso_{anio_hueso}.xlsx")

        m1, m2 = st.columns(2)
        m1.metric("Capital Inmovilizado", f"₡ {total_atrapado/1e6:,.1f} M")
        m2.metric("Items Sin Rotación", len(df_zombies))
        
        st.dataframe(
            df_zombies[['Producto', 'create_date', 'Stock', 'Costo', 'Valor_Inventario']].head(50)
            .style.format({'Costo': '₡ {:,.0f}', 'Valor_Inventario': '₡ {:,.0f}', 'create_date': '{:%Y-%m-%d}'}),
            use_container_width=True
        )

# === PESTAÑA 5: SEGMENTACIÓN CLIENTES ===
with tab_cli:
    if not df_main.empty:
        st.subheader("🌍 Distribución de Ventas")
        anio_c_sel = st.selectbox("Año de Análisis", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        
        col_geo1, col_geo2, col_cat = st.columns(3)
        
        with col_geo1:
            st.markdown("**Por Provincia**")
            ventas_prov = df_c_anio.groupby('Provincia')['Venta_Neta'].sum().reset_index()
            fig_prov = px.pie(ventas_prov, values='Venta_Neta', names='Provincia', hole=0.4)
            st.plotly_chart(fig_prov, use_container_width=True)
            
        with col_geo2:
            st.markdown("**Por Zona (Studio)**")
            ventas_zona = df_c_anio.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index()
            fig_zona = px.pie(ventas_zona, values='Venta_Neta', names='Zona_Comercial', hole=0.4)
            st.plotly_chart(fig_zona, use_container_width=True)
            
        with col_cat:
            st.markdown("**Por Categoría**")
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
            else:
                st.success("Retención del 100%.")

# === PESTAÑA 6: VENDEDORES ===
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
            else:
                st.info("Sin ventas registradas.")
                
        with col_v_lost:
            st.subheader("⚠️ Cartera Perdida")
            if perdidos_v:
                df_lost_v = df_v_ant[df_v_ant['Cliente'].isin(perdidos_v)]
                top_lost_v = df_lost_v.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                fig_vl = px.bar(top_lost_v, x=top_lost_v.values, y=top_lost_v.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])
                fig_vl.update_layout(xaxis_title="Monto Comprado Año Anterior")
                st.plotly_chart(fig_vl, use_container_width=True)
            else:
                st.success(f"Excelente retención.")

# === PESTAÑA 7: RADIOGRAFÍA CLIENTE ===
with tab_det:
    if not df_main.empty:
        st.header("🔍 Radiografía Individual")
        
        clientes_todos = sorted(df_main['Cliente'].unique())
        cliente_sel = st.selectbox("Escribe para buscar cliente:", clientes_todos, index=None, placeholder="Ej: Corporación...")
        
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
                st.subheader("📅 Historial Anual")
                hist = df_cli.groupby(df_cli['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                hist.columns = ['Año', 'Venta']
                fig_h = px.bar(hist, x='Año', y='Venta', text_auto='.2s', color='Venta')
                fig_h.update_xaxes(type='category')
                st.plotly_chart(fig_h, use_container_width=True)
            
            with c_prod:
                st.subheader("📦 Productos Favoritos (Top 10)")
                metrica_cli = st.radio("Ver por:", ["Monto", "Cantidad"], horizontal=True, key="metrica_cli", label_visibility="collapsed")
                
                if not df_prod.empty:
                    ids_facturas = df_cli['id'].tolist() if 'id' in df_cli.columns else []
                    if not ids_facturas: ids_facturas = [] 

                    df_prod_cli = df_prod[df_prod['ID_Factura'].isin(df_cli['ID_Cliente'].unique())] if 'ID_Factura' in df_prod.columns else pd.DataFrame()
                    
                    if df_prod_cli.empty and not df_cli.empty:
                         nombres_movs = df_cli['name'].unique()
                         df_prod_cli = df_prod[df_prod['move_name'].isin(nombres_movs)] if 'move_name' in df_prod.columns else pd.DataFrame()

                    if not df_prod_cli.empty:
                        col_orden = 'Venta_Neta' if metrica_cli == "Monto" else 'quantity'
                        top_p_cli = df_prod_cli.groupby('Producto')[[col_orden]].sum().sort_values(col_orden, ascending=False).head(10).sort_values(col_orden, ascending=True)
                        fig_p = px.bar(top_p_cli, x=col_orden, y=top_p_cli.index, orientation='h', text_auto='.2s', color=col_orden)
                        st.plotly_chart(fig_p, use_container_width=True)
                        
                        df_hist_prod = df_prod_cli.groupby(['date', 'Producto'])[['quantity', 'Venta_Neta']].sum().reset_index().sort_values('date', ascending=False)
                        st.download_button("📥 Descargar Historial", data=convert_df_to_excel(df_hist_prod), file_name=f"Historial_{cliente_sel}.xlsx")
                    else:
                        st.info("No se encontraron detalles de productos.")
