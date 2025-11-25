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
    """Descarga CATÁLOGO COMPLETO (Activos)"""
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # 1. KITS FANTASMA (Para excluirlos)
        try:
            ids_kits = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'search', [[['type', '=', 'phantom']]])
            kits_data = models.execute_kw(DB, uid, PASSWORD, 'mrp.bom', 'read', [ids_kits], {'fields': ['product_tmpl_id']})
            ids_templates_kit = [k['product_tmpl_id'][0] for k in kits_data if k['product_tmpl_id']]
        except:
            ids_templates_kit = []

        # 2. CATÁLOGO (Traemos TODO lo activo para saber tipos, aunque stock sea 0)
        dominio = [['active', '=', True]]
        campos = ['name', 'qty_available', 'list_price', 'standard_price', 'detailed_type', 'create_date', 'product_tmpl_id']
        
        ids = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['create_date'] = pd.to_datetime(df['create_date'])
            # Cálculo de Valor de Inventario (Costo * Cantidad)
            df['Valor_Inventario'] = df['qty_available'] * df['standard_price']
            
            df.rename(columns={'id': 'ID_Producto', 'name': 'Producto', 'qty_available': 'Stock', 'standard_price': 'Costo'}, inplace=True)
            
            # Filtro Kits
            df['ID_Template'] = df['product_tmpl_id'].apply(lambda x: x[0] if x else 0)
            if ids_templates_kit:
                df = df[~df['ID_Template'].isin(ids_templates_kit)]

            # Mapeo Tipos
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

with st.spinner('Sincronizando Odoo...'):
    df_main = cargar_datos_generales()
    df_prod = cargar_detalle_productos()
    df_cat = cargar_inventario() # Catálogo completo
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
    if not df_prod.empty and not df_cat.empty:
        anios_p = sorted(df_prod['date'].dt.year.unique(), reverse=True)
        anio_p_sel = st.selectbox("Año de Análisis", anios_p, key="prod_anio")
        
        # Cruzamos VENTAS con CATÁLOGO para saber Tipos
        df_p_anio = df_prod[df_prod['date'].dt.year == anio_p_sel].copy()
        df_p_anio = pd.merge(df_p_anio, df_cat[['ID_Producto', 'Tipo']], on='ID_Producto', how='left')
        df_p_anio['Tipo'] = df_p_anio['Tipo'].fillna('Desconocido')

        # FILTRO: Solo Almacenable y Servicio (Adiós Consumibles)
        df_p_anio = df_p_anio[df_p_anio['Tipo'].isin(['Almacenable', 'Servicio'])]

        st.subheader("📦 Desempeño de Producto (Sin Consumibles)")
        col_tipo1, col_tipo2 = st.columns([1, 2])
        
        with col_tipo1:
            ventas_por_tipo = df_p_anio.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            fig_pie = px.pie(ventas_por_tipo, values='Venta_Neta', names='Tipo', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(height=350, title_text="Mix de Venta")
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_tipo2:
            st.markdown(f"**Top 10 Productos ({anio_p_sel})**")
            # Filtro visual por si quieres ver solo uno
            tipo_ver = st.radio("Ver:", ["Todos", "Almacenable", "Servicio"], horizontal=True)
            df_show = df_p_anio if tipo_ver == "Todos" else df_p_anio[df_p_anio['Tipo'] == tipo_ver]
            
            top_prod = df_show.groupby('Producto')[['Venta_Neta', 'quantity']].sum().reset_index()
            top_10 = top_prod.sort_values('Venta_Neta', ascending=False).head(10).sort_values('Venta_Neta', ascending=True)
            
            fig_bar = px.bar(top_10, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s', color='Venta_Neta')
            fig_bar.update_layout(height=350, xaxis_title="Monto", yaxis_title="")
            st.plotly_chart(fig_bar, use_container_width=True)
        
        st.divider()
        
        # --- ZOMBIES (HUESOS) ---
        st.subheader("⚠️ Alerta: Productos Hueso (Capital Atrapado)")
        
        # 1. Filtramos el catálogo para ver solo lo que tiene STOCK FÍSICO REAL
        df_stock_real = df_cat[df_cat['Stock'] > 0].copy()
        
        # 2. Identificamos qué se vendió en el año seleccionado
        ids_vendidos = set(df_p_anio['ID_Producto'].unique())
        
        # 3. Filtro Hueso: Tienen stock pero NO están en la lista de vendidos
        df_zombies = df_stock_real[~df_stock_real['ID_Producto'].isin(ids_vendidos)].copy()
        
        # 4. Filtro Novedad: Excluir creados en el mismo año de análisis
        df_zombies = df_zombies[df_zombies['create_date'].dt.year < anio_p_sel]
        
        # 5. Solo Almacenables (Servicios no tienen stock)
        df_zombies = df_zombies[df_zombies['Tipo'] == 'Almacenable']
        
        # Ordenar por Dinero
        df_zombies = df_zombies.sort_values('Valor_Inventario', ascending=False)
        total_atrapado = df_zombies['Valor_Inventario'].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Capital Inmovilizado (Costo)", f"₡ {total_atrapado/1e6:,.1f} M", help="Stock x Costo")
        m2.metric("Items Hueso", len(df_zombies))
        
        st.write(f"Top Productos estancados en {anio_p_sel} (Ordenado por Valor de Inventario):")
        # Tabla Limpia sin List Price, con Costo y Valor Total
        st.dataframe(
            df_zombies[['Producto', 'create_date', 'Stock', 'Costo', 'Valor_Inventario']].head(50)
            .style.format({'Costo': '₡ {:,.0f}', 'Valor_Inventario': '₡ {:,.0f}', 'create_date': '{:%Y-%m-%d}'}),
            use_container_width=True
        )

# === PESTAÑA 3: CLIENTES ===
with tab_cli:
    if not df_main.empty:
        anio_c_sel = st.selectbox("Año", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        df_c_ant = df_main[df_main['invoice_date'].dt.year == (anio_c_sel - 1)]
        
        cli_antes = set(df_c_ant[df_c_ant['Venta_Neta'] > 0]['Cliente'])
        cli_ahora = set(df_c_anio[df_c_anio['Venta_Neta'] > 0]['Cliente'])
        perdidos = list(cli_antes - cli_ahora)
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Clientes Activos", len(cli_ahora))
        k2.metric("Nuevos", len(cli_ahora - cli_antes))
        k3.metric("Perdidos", len(perdidos), delta=-len(perdidos), delta_color="inverse")
        
        st.divider()
        
        c_p, c_r = st.columns([2, 1])
        with c_p:
            st.subheader("Top Clientes")
            top_c = df_c_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(15)
            fig_c = px.bar(top_c, x=top_c.values, y=top_c.index, orientation='h', text_auto='.2s')
            st.plotly_chart(fig_c, use_container_width=True)
            
        with c_r:
            st.subheader("Clientes Perdidos (Top Valor)")
            if perdidos:
                df_lost = df_c_ant[df_c_ant['Cliente'].isin(perdidos)]
                st.dataframe(df_lost.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(20).to_frame().style.format("₡ {:,.0f}"))
