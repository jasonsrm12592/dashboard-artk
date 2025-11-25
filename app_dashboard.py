import streamlit as st
import pandas as pd
import xmlrpc.client
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
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

# --- 2. CREDENCIALES ---
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    COMPANY_ID = st.secrets["odoo"]["company_id"]
except Exception:
    st.error("❌ Error: No encuentro el archivo .streamlit/secrets.toml")
    st.stop()

# --- 3. FUNCIONES DE CARGA ---

@st.cache_data(ttl=900) 
def cargar_datos_generales():
    """Descarga FACTURAS (Encabezados)"""
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
            df['Cliente'] = df['partner_id'].apply(lambda x: x[1] if x else "Sin Cliente")
            df['Vendedor'] = df['invoice_user_id'].apply(lambda x: x[1] if x else "Sin Asignar")
            df['Venta_Neta'] = df['amount_untaxed_signed']
            
            # Limpieza
            df = df[~df['name'].str.contains("WT-", case=False, na=False)]
            
        return df
    except Exception as e:
        st.error(f"Error Odoo Facturas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600) 
def cargar_detalle_productos():
    """Descarga LÍNEAS DE FACTURA (Ventas)"""
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
        campos = ['date', 'product_id', 'credit', 'debit', 'quantity', 'name']
        
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['ID_Producto'] = df['product_id'].apply(lambda x: x[0] if x else 0)
            df['Producto'] = df['product_id'].apply(lambda x: x[1] if x else "Otros")
            df['Venta_Neta'] = df['credit'] - df['debit']
            
        return df
    except Exception as e:
        st.error(f"Error Odoo Productos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_inventario():
    """Descarga STOCK y filtra KITS"""
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
        campos = ['name', 'qty_available', 'list_price', 'standard_price', 'detailed_type', 'create_date', 'product_tmpl_id']
        
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['create_date'] = pd.to_datetime(df['create_date'])
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo'}, inplace=True)
            
            df['ID_Template'] = df['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
            if ids_templates_kit:
                df = df[~df['ID_Template'].isin(ids_templates_kit)]

            tipo_map = {'product': 'Almacenable', 'service': 'Servicio', 'consu': 'Consumible'}
            df['Tipo'] = df['detailed_type'].map(tipo_map).fillna('Otro')
            
        return df
    except Exception as e:
        st.error(f"Error Odoo Inventario: {e}")
        return pd.DataFrame()

def cargar_metas():
    if os.path.exists("metas.xlsx"):
        df = pd.read_excel("metas.xlsx")
        df['Mes'] = pd.to_datetime(df['Mes'])
        return df
    return pd.DataFrame({'Mes': [], 'Meta': []})

# --- 4. INTERFAZ ---
st.title("🚀 Monitor Comercial ALROTEK")

tab_kpis, tab_prod, tab_cli = st.tabs(["📊 Visión General", "📦 Productos & Inventario", "👥 Análisis Clientes"])

with st.spinner('Procesando datos (Ventas + Inventario + Clientes)...'):
    df_main = cargar_datos_generales()
    df_prod = cargar_detalle_productos()
    df_stock = cargar_inventario()
    df_metas = cargar_metas()

# === PESTAÑA 1: GENERAL ===
with tab_kpis:
    if not df_main.empty:
        anios = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        anio_sel = st.selectbox("Año Fiscal", anios, key="kpi_anio")
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_sel]
        
        venta = df_anio['Venta_Neta'].sum()
        meta = df_metas[df_metas['Mes'].dt.year == anio_sel]['Meta'].sum()
        
        cant_facturas = df_anio['name'].nunique()
        ticket_promedio = (venta / cant_facturas) if cant_facturas > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Venta Total", f"₡ {venta/1e6:,.1f} M")
        c2.metric("Meta Anual", f"₡ {meta/1e6:,.1f} M", f"Falta: {(meta-venta)/1e6:,.1f}M")
        c3.metric("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%")
        c4.metric("Ticket Promedio", f"₡ {ticket_promedio:,.0f}", f"{cant_facturas} Ops")

        st.divider()
        
        c_graf, c_vend = st.columns([2, 1])
        with c_graf:
            v_mes = df_anio.groupby('Mes')['Venta_Neta'].sum().reset_index()
            dash = pd.merge(v_mes, df_metas, left_on='Mes', right_on='Mes', how='left').fillna(0)
            cols = ['#27ae60' if r >= m else '#c0392b' for r, m in zip(dash['Venta_Neta'], dash['Meta'])]
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=dash['Mes'], y=dash['Venta_Neta'], name='Venta', marker_color=cols))
            fig.add_trace(go.Scatter(x=dash['Mes'], y=dash['Meta'], name='Meta', line=dict(color='#f1c40f', width=4, dash='dash')))
            fig.update_layout(title="Evolución Mensual", height=400, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            
        with c_vend:
            st.subheader("🏆 Top Vendedores")
            rank = df_anio.groupby('Vendedor')['Venta_Neta'].sum().sort_values().tail(10)
            fig_v = go.Figure(go.Bar(x=rank.values, y=rank.index, orientation='h', text=rank.apply(lambda x: f'{x/1e6:.1f}M'), textposition='auto'))
            fig_v.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_v, use_container_width=True)

# === PESTAÑA 2: PRODUCTOS ===
with tab_prod:
    if not df_prod.empty and not df_stock.empty:
        anios_p = sorted(df_prod['date'].dt.year.unique(), reverse=True)
        anio_p_sel = st.selectbox("Año de Análisis", anios_p, key="prod_anio")
        
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_p_sel].copy()
        df_p_anio = pd.merge(df_p_anio, df_stock[['ID_Producto', 'Tipo']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')
        
        # Filtro Consumibles
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]

        col_tipo1, col_tipo2 = st.columns([1, 2])
        
        with col_tipo1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(height=350, title_text="Mix de Venta")
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_tipo2:
            st.markdown(f"**Top 10 Productos ({anio_p_sel})**")
            tipo_ver = st.radio("Ver:", ["Todos", "Almacenable", "Servicio"], horizontal=True)
            df_show = df_p_anio if tipo_ver == "Todos" else df_p_anio[df_p_anio['Tipo'] == tipo_ver]
            top_prod = df_show.groupby('Producto')[['Venta_Neta', 'quantity']].sum().reset_index()
            top_10 = top_prod.sort_values('Venta_Neta', ascending=False).head(10).sort_values('Venta_Neta', ascending=True)
            
            fig_bar = px.bar(top_10, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s', color='Venta_Neta')
            fig_bar.update_layout(height=350, xaxis_title="Monto", yaxis_title="")
            st.plotly_chart(fig_bar, use_container_width=True)
        
        st.divider()
        
        # ZOMBIES
        st.subheader("⚠️ Alerta: Productos Hueso (Capital Atrapado)")
        df_stock_real = df_stock[df_stock['Stock'] > 0].copy()
        ids_vendidos = set(df_p_anio['ID_Producto'].unique())
        df_zombies = df_stock_real[~df_stock_real['ID_Producto'].isin(ids_vendidos)].copy()
        df_zombies = df_zombies[df_zombies['create_date'].dt.year < anio_p_sel]
        df_zombies = df_zombies[df_zombies['Tipo'] == 'Almacenable']
        df_zombies = df_zombies.sort_values('Valor_Inventario', ascending=False)
        total_atrapado = df_zombies['Valor_Inventario'].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Capital Inmovilizado (Costo)", f"₡ {total_atrapado/1e6:,.1f} M", help="Stock x Costo")
        m2.metric("Items Hueso", len(df_zombies))
        
        st.write(f"Top Productos estancados en {anio_p_sel}:")
        st.dataframe(
            df_zombies[['Producto', 'create_date', 'Stock', 'Costo', 'Valor_Inventario']].head(50)
            .style.format({'Costo': '₡ {:,.0f}', 'Valor_Inventario': '₡ {:,.0f}', 'create_date': '{:%Y-%m-%d}'}),
            use_container_width=True
        )

# === PESTAÑA 3: CLIENTES (MEJORADA) ===
with tab_cli:
    if not df_main.empty:
        anio_c_sel = st.selectbox("Año", anios, key="cli_anio")
        
        # Datos Año Actual y Anterior
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        df_c_ant = df_main[df_main['invoice_date'].dt.year == (anio_c_sel - 1)]
        
        # Identificar Clientes
        cli_antes = set(df_c_ant[df_c_ant['Venta_Neta'] > 0]['Cliente'])
        cli_ahora = set(df_c_anio[df_c_anio['Venta_Neta'] > 0]['Cliente'])
        
        # Cálculos de Pérdida y Ganancia
        lista_perdidos = list(cli_antes - cli_ahora)
        lista_nuevos = list(cli_ahora - cli_antes)
        
        # Montos Financieros de esa pérdida/ganancia
        monto_perdido = 0
        if lista_perdidos:
            df_lost = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]
            monto_perdido = df_lost['Venta_Neta'].sum()
            
        monto_nuevo = 0
        if lista_nuevos:
            df_new = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]
            monto_nuevo = df_new['Venta_Neta'].sum()
        
        # KPIs Clientes
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Clientes Activos", len(cli_ahora))
        k2.metric("Clientes Nuevos", len(lista_nuevos))
        k3.metric("Venta de Nuevos", f"₡ {monto_nuevo/1e6:,.1f} M", help="Lo que han comprado los clientes nuevos este año")
        k4.metric("Oportunidad Perdida", f"₡ {monto_perdido/1e6:,.1f} M", help="Lo que compraron el año pasado los clientes que se fueron", delta_color="inverse")
        
        st.divider()
        
        col_new, col_lost = st.columns(2)
        
        with col_new:
            st.subheader("🌱 Top Clientes Nuevos")
            if lista_nuevos:
                df_new_rank = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]
                top_new = df_new_rank.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(20)
                st.dataframe(top_new.to_frame("Venta Acumulada").style.format("₡ {:,.0f}"), use_container_width=True)
            else:
                st.info("No hay clientes nuevos en este periodo.")
                
        with col_lost:
            st.subheader("⚠️ Top Clientes Perdidos")
            if lista_perdidos:
                df_lost_rank = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]
                top_lost = df_lost_rank.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(20)
                st.dataframe(top_lost.to_frame("Compra Año Anterior").style.format("₡ {:,.0f}"), use_container_width=True)
            else:
                st.success("¡Felicidades! Retención del 100%.")

        st.divider()
        
        # Gráfico de Dispersión
        st.subheader("🔎 Matriz de Valor: Frecuencia vs Monto")
        scatter_data = df_c_anio.groupby('Cliente').agg({'Venta_Neta': 'sum', 'name': 'nunique'}).reset_index()
        scatter_data.columns = ['Cliente', 'Monto', 'Frecuencia']
        # Fix tamaño burbujas
        scatter_data['Size'] = scatter_data['Monto'].abs().replace(0, 1)
        
        fig_s = px.scatter(scatter_data, x='Frecuencia', y='Monto', size='Size', 
                           color='Monto', hover_name='Cliente', color_continuous_scale='RdBu')
        st.plotly_chart(fig_s, use_container_width=True)
