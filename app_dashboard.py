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

# --- 3. FUNCIONES UTILITARIAS ---
def convert_df_to_excel(df):
    """Convierte DataFrame a Excel en memoria"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
    return output.getvalue()

# --- 4. FUNCIONES DE CARGA ---

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
        
        # Traemos 'id' explícitamente (aunque read lo trae por defecto)
        campos = ['name', 'invoice_date', 'amount_untaxed_signed', 'partner_id', 'invoice_user_id']
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['Mes'] = df['invoice_date'].dt.to_period('M').dt.to_timestamp()
            df['Mes_Num'] = df['invoice_date'].dt.month
            df['Cliente'] = df['partner_id'].apply(lambda x: x[1] if x else "Sin Cliente")
            # Guardamos ID Cliente para cruce con zonas
            df['ID_Cliente'] = df['partner_id'].apply(lambda x: x[0] if x else 0)
            df['Vendedor'] = df['invoice_user_id'].apply(lambda x: x[1] if x else "Sin Asignar")
            df['Venta_Neta'] = df['amount_untaxed_signed']
            
            # Limpieza
            df = df[~df['name'].str.contains("WT-", case=False, na=False)]
            
        return df
    except Exception as e:
        st.error(f"Error Odoo Facturas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_zonas_clientes(ids_clientes):
    """Descarga la ZONA (Provincia) de los clientes"""
    try:
        if not ids_clientes: return pd.DataFrame()
        
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        campos = ['state_id'] 
        registros = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'read', [list(ids_clientes)], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['Zona'] = df['state_id'].apply(lambda x: x[1] if x else "Sin Zona")
            # Renombrar id para cruce
            df.rename(columns={'id': 'ID_Cliente'}, inplace=True)
            return df[['ID_Cliente', 'Zona']]
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
        # IMPORTANTE: Traer 'move_id' para cruzar con la factura
        campos = ['date', 'product_id', 'credit', 'debit', 'quantity', 'name', 'move_id']
        
        ids = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'search', [dominio])
        registros = models.execute_kw(DB, uid, PASSWORD, 'account.move.line', 'read', [ids], {'fields': campos})
        
        df = pd.DataFrame(registros)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['ID_Producto'] = df['product_id'].apply(lambda x: x[0] if x else 0)
            df['Producto'] = df['product_id'].apply(lambda x: x[1] if x else "Otros")
            
            # ID FACTURA PADRE (La clave del cruce)
            df['ID_Factura'] = df['move_id'].apply(lambda x: x[0] if x else 0)
            
            df['Venta_Neta'] = df['credit'] - df['debit']
            
        return df
    except Exception as e:
        st.error(f"Error Odoo Productos: {e}")
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
        df['Mes_Num'] = df['Mes'].dt.month
        df['Anio'] = df['Mes'].dt.year
        return df
    return pd.DataFrame({'Mes': [], 'Meta': [], 'Mes_Num': [], 'Anio': []})

# --- 5. INTERFAZ ---
st.title("🚀 Monitor Comercial ALROTEK")

tab_kpis, tab_prod, tab_inv, tab_cli, tab_vend, tab_det = st.tabs([
    "📊 Visión General", 
    "📦 Ventas por Producto", 
    "🧟 Control Inventario", 
    "👥 Inteligencia Clientes",
    "💼 Desempeño Vendedores",
    "🔍 Detalle Cliente"
])

with st.spinner('Sincronizando todo...'):
    df_main = cargar_datos_generales()
    df_prod = cargar_detalle_productos()
    df_cat = cargar_inventario()
    df_metas = cargar_metas()
    
    # Cargar Zonas (Provincias)
    if not df_main.empty:
        ids_unicos = df_main['ID_Cliente'].unique().tolist()
        df_zonas = cargar_zonas_clientes(ids_unicos)
        if not df_zonas.empty:
            df_main = pd.merge(df_main, df_zonas, on='ID_Cliente', how='left')
            df_main['Zona'] = df_main['Zona'].fillna('Sin Zona')
        else:
            df_main['Zona'] = 'Sin Zona'

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
            excel_data = convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'Zona', 'Vendedor', 'Venta_Neta']])
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
            tipo_ver = st.radio("Ver:", ["Todos", "Almacenable", "Servicio"], horizontal=True)
            df_show = df_p_anio if tipo_ver == "Todos" else df_p_anio[df_p_anio['Tipo'] == tipo_ver]
            
            top_prod = df_show.groupby('Producto')[['Venta_Neta', 'quantity']].sum().reset_index()
            top_10 = top_prod.sort_values('Venta_Neta', ascending=False).head(10).sort_values('Venta_Neta', ascending=True)
            
            fig_bar = px.bar(top_10, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s', color='Venta_Neta')
            fig_bar.update_layout(height=350, xaxis_title="Monto", yaxis_title="")
            st.plotly_chart(fig_bar, use_container_width=True)

# === PESTAÑA 3: INVENTARIO ===
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

# === PESTAÑA 4: CLIENTES ===
with tab_cli:
    if not df_main.empty:
        anio_c_sel = st.selectbox("Año de Análisis", anios, key="cli_anio")
        df_c_anio = df_main[df_main['invoice_date'].dt.year == anio_c_sel]
        df_c_ant = df_main[df_main['invoice_date'].dt.year == (anio_c_sel - 1)]
        
        cli_antes = set(df_c_ant[df_c_ant['Venta_Neta'] > 0]['Cliente'])
        cli_ahora = set(df_c_anio[df_c_anio['Venta_Neta'] > 0]['Cliente'])
        
        lista_perdidos = list(cli_antes - cli_ahora)
        lista_nuevos = list(cli_ahora - cli_antes)
        
        monto_perdido = 0
        if lista_perdidos:
            monto_perdido = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)]['Venta_Neta'].sum()
            
        monto_nuevo = 0
        if lista_nuevos:
            monto_nuevo = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]['Venta_Neta'].sum()
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Clientes Activos", len(cli_ahora))
        k2.metric("Clientes Nuevos", len(lista_nuevos))
        k3.metric("Venta de Nuevos", f"₡ {monto_nuevo/1e6:,.1f} M")
        k4.metric("Venta Perdida (Churn)", f"₡ {monto_perdido/1e6:,.1f} M", delta=-len(lista_perdidos), delta_color="inverse")
        
        st.divider()
        
        # Descargas
        st.subheader("📥 Descargar Reportes")
        col_d1, col_d2, col_d3 = st.columns(3)
        
        df_top_all = df_c_anio.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
        excel_top = convert_df_to_excel(df_top_all)
        col_d1.download_button("📂 Ranking Completo", data=excel_top, file_name=f"Ranking_Clientes_{anio_c_sel}.xlsx")
            
        if lista_perdidos:
            df_lost_all = df_c_ant[df_c_ant['Cliente'].isin(lista_perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
            df_lost_all.columns = ['Cliente', 'Compra_Año_Anterior']
            excel_lost = convert_df_to_excel(df_lost_all)
            col_d2.download_button("📉 Clientes Perdidos", data=excel_lost, file_name=f"Clientes_Perdidos_{anio_c_sel}.xlsx")
                
        if lista_nuevos:
            df_new_all = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
            df_new_all.columns = ['Cliente', 'Venta_Actual']
            excel_new = convert_df_to_excel(df_new_all)
            col_d3.download_button("🌱 Clientes Nuevos", data=excel_new, file_name=f"Clientes_Nuevos_{anio_c_sel}.xlsx")

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

        st.subheader("🌱 Top Clientes Nuevos")
        if lista_nuevos:
            df_new = df_c_anio[df_c_anio['Cliente'].isin(lista_nuevos)]
            top_new = df_new.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
            fig_new = px.bar(top_new, x=top_new.values, y=top_new.index, orientation='h', text_auto='.2s', color_discrete_sequence=['#2ecc71'])
            st.plotly_chart(fig_new, use_container_width=True)

# === PESTAÑA 5: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        st.header("💼 Análisis de Desempeño Individual")
        
        anios_v = sorted(df_main['invoice_date'].dt.year.unique(), reverse=True)
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            anio_v_sel = st.selectbox("Año de Evaluación", anios_v, key="vend_anio")
        
        lista_vendedores = sorted(df_main['Vendedor'].unique())
        with col_sel2:
            vendedor_sel = st.selectbox("Seleccionar Comercial", lista_vendedores)
            
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
                df_llamadas.columns = ['Cliente', 'Compra_Año_Pasado']
                excel_call = convert_df_to_excel(df_llamadas)
                st.download_button(f"📞 Descargar Lista Recuperación", data=excel_call, file_name=f"Recuperar_{vendedor_sel}.xlsx")

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

# === PESTAÑA 6: DETALLE CLIENTE ===
with tab_det:
    if not df_main.empty:
        st.header("🔍 Radiografía por Cliente")
        
        zonas = ["Todas"] + sorted(list(df_main['Zona'].dropna().unique()))
        zona_sel = st.selectbox("Filtrar por Zona", zonas)
        
        df_zona = df_main if zona_sel == "Todas" else df_main[df_main['Zona'] == zona_sel]
        clientes_zona = sorted(df_zona['Cliente'].unique())
        cliente_sel = st.selectbox("Seleccionar Cliente", clientes_zona)
        
        if cliente_sel:
            df_cli = df_main[df_main['Cliente'] == cliente_sel]
            total_comprado = df_cli['Venta_Neta'].sum()
            ultima_compra = df_cli['invoice_date'].max()
            dias_sin = (datetime.now() - ultima_compra).days
            
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Compras Históricas", f"₡ {total_comprado/1e6:,.1f} M")
            kc2.metric("Última Compra", ultima_compra.strftime('%d-%m-%Y'))
            kc3.metric("Días sin Comprar", dias_sin, delta=-dias_sin, delta_color="inverse")
            
            st.divider()
            
            c_hist, c_prod = st.columns([1, 1])
            
            with c_hist:
                st.subheader("📅 Historial Anual")
                hist = df_cli.groupby(df_cli['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                hist.columns = ['Año', 'Venta']
                fig_h = px.bar(hist, x='Año', y='Venta', text_auto='.2s')
                fig_h.update_xaxes(type='category')
                st.plotly_chart(fig_h, use_container_width=True)
                
            with c_prod:
                st.subheader("📦 Productos Favoritos (Top 10)")
                if not df_prod.empty:
                    ids_facturas = set(df_cli['id'].unique()) # Usamos el ID de factura que cargamos
                    # Filtramos las líneas de producto que pertenecen a esas facturas
                    # IMPORTANTE: df_prod tiene 'ID_Factura' gracias a la función de carga actualizada
                    df_prod_cli = df_prod[df_prod['ID_Factura'].isin(ids_facturas)]
                    
                    if not df_prod_cli.empty:
                        top_p_cli = df_prod_cli.groupby('Producto')['Venta_Neta'].sum().sort_values(ascending=False).head(10).sort_values(ascending=True)
                        fig_p = px.bar(top_p_cli, x='Venta_Neta', y=top_p_cli.index, orientation='h', text_auto='.2s')
                        st.plotly_chart(fig_p, use_container_width=True)
                    else:
                        st.info("No se encontraron detalles de productos (Rango de fechas limitado).")
                else:
                    st.warning("Cargando productos...")
