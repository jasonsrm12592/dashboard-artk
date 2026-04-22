import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import ast
import io

# Importar módulos locales
import config
import services
import ui

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Alrotek Monitor v1", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# HELPER: Gráfico de Pastel Mejorado
def create_improved_pie(df_in, col_val, col_name, title, threshold=0.02, show_percent_only=True, prefix="", suffix=""):
    # Agrupar y ordenar
    df_g = df_in.groupby(col_name)[col_val].sum().reset_index().sort_values(col_val, ascending=False)
    
    # Calcular %
    total = df_g[col_val].sum()
    if total == 0: return go.Figure()
    
    # Agrupar menores
    mask = (df_g[col_val] / total) < threshold
    if mask.any():
        otros = df_g[mask][col_val].sum()
        df_g = df_g[~mask].copy()
        df_g = pd.concat([df_g, pd.DataFrame({col_name: ['Otros/Menores'], col_val: [otros]})], ignore_index=True)

    # Recalcular porcentajes finales
    df_g['Pct'] = (df_g[col_val] / total * 100).round(1)
    
    # Formatear nombres para la leyenda (Nombre - Monto (Pct%))
    def fmt_v(v):
        if abs(v) >= 1e6: return f"{v/1e6:.1f}M"
        if abs(v) >= 1e3: return f"{v/1e3:.1f}k"
        return f"{v:,.0f}"
        
    df_g[col_name] = df_g.apply(lambda r: f"{r[col_name]} - {prefix}{fmt_v(r[col_val])}{suffix} ({r['Pct']}%)", axis=1)
    
    # Crear gráfico
    fig = px.pie(df_g, values=col_val, names=col_name, title=title, hole=0.4)
    
    # Configurar layout: Leyenda VERTICAL a la derecha
    info_mode = 'percent' if show_percent_only else 'percent+label'
    fig.update_traces(textposition='inside', textinfo=info_mode)
    fig.update_layout(legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05))
    
    return fig


# --- 1.2 INICIALIZACIÓN DE ESTADO ---
if 'tc_usd' not in st.session_state:
    st.session_state.tc_usd = float(services.get_current_usd_rate())
tc_usd = st.session_state.tc_usd

# Cargar estilos
ui.load_styles()

# --- 5. INTERFAZ ---
st.image("logo.png", width=100)
st.title("Alrotek Monitor v1")

# SE AGREGÓ 'tab_config' AL FINAL
tab_kpis, tab_renta, tab_prod, tab_inv, tab_cx, tab_cli, tab_vend, tab_det, tab_config = st.tabs(["📊 Visión General", "📈 Rentabilidad Proyectos", "📦 Productos", "🕸️ Baja Rotación", "💰 Cartera", "👥 Segmentación", "💼 Vendedores", "🔍 Radiografía", "⚙️ Config"])

# === PESTAÑA: CONFIGURACIÓN (REUBICADA AL INICIO DE LA LÓGICA) ===
with tab_config:
    st.header("⚙️ Configuración Global")
    st.markdown("Ajusta los parámetros que afectan a todo el dashboard.")
    
    st.subheader("💹 Moneda y Tipo de Cambio")
    # El valor se sincroniza automáticamente con st.session_state.tc_usd por el 'key'
    st.number_input("Tipo de Cambio (USD -> CRC)", key="tc_usd", format="%.2f")
    
    st.info(f"💡 **Dato de Odoo**: El tipo de cambio actual en el sistema es ₡{services.get_current_usd_rate():,.2f}")
    st.caption("Nota: Cambiar este valor actualizará todos los cálculos de conversión a dólares en las demás pestañas.")

with st.spinner('Cargando...'):
    df_main = services.cargar_datos_generales()
    df_metas = services.cargar_metas()
    df_prod = services.cargar_detalle_productos()
    df_an = services.cargar_estructura_analitica()
    
    if not df_main.empty:
        df_info = services.cargar_datos_clientes_extendido(df_main['ID_Cliente'].unique().tolist())
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
        
        venta = df_anio['Venta_Neta_USD'].sum()
        delta = ((venta - df_ant['Venta_Neta_USD'].sum()) / df_ant['Venta_Neta_USD'].sum() * 100) if df_ant['Venta_Neta_USD'].sum() > 0 else 0
        meta = df_metas[df_metas['Anio'] == anio_sel]['Dolares'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: ui.card_kpi("Venta Total (USD)", venta, "border-green", f"{delta:+.1f}% vs Anterior", formato="usd")
        with c2: ui.card_kpi("Meta Anual (USD)", meta, "bg-dark-blue", formato="usd")
        with c3: ui.card_kpi("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%", "border-blue", formato="raw")
        with c4: ui.card_kpi("Ticket Prom. (USD)", (venta/df_anio['name'].nunique()) if df_anio['name'].nunique()>0 else 0, "border-purple", formato="usd")
        
        st.divider()

        st.markdown(f"### 🎯 Cumplimiento de Meta USD ({anio_sel})")
        v_act = df_anio.groupby('Mes_Num')['Venta_Neta_USD'].sum().reset_index().rename(columns={'Venta_Neta_USD': 'Actual'})
        v_meta = df_metas[df_metas['Anio'] == anio_sel].groupby('Mes_Num')['Dolares'].sum().reset_index().rename(columns={'Dolares': 'Meta'})
        df_gm = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_meta, on='Mes_Num', how='left').fillna(0)
        df_gm['Mes'] = df_gm['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        def lbl_meta(r):
            act, meta = r['Actual'], r['Meta']
            def fm(v):
                av = abs(v)
                if av >= 1e6: return f"${av/1e6:.1f}M"
                elif av >= 1e3: return f"${av/1e3:.0f}k"
                return f"${av:.0f}"
            t = fm(act)
            if meta > 0:
                d = act - meta
                s = "+" if d >= 0 else "-"
                t += f"<br>({s}{fm(d)})"
            return t
            
        df_gm['Label'] = df_gm.apply(lbl_meta, axis=1)
        
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=df_gm['Mes'], y=df_gm['Actual'], name='Actual (USD)', 
                               marker_color=['#2ecc71' if r>=m else '#e74c3c' for r,m in zip(df_gm['Actual'], df_gm['Meta'])],
                               text=df_gm['Label'], textposition='auto'))
        fig_m.add_trace(go.Scatter(x=df_gm['Mes'], y=df_gm['Meta'], name='Meta (USD)', line=dict(color='#f1c40f', width=3, dash='dash')))
        st.plotly_chart(ui.config_plotly(fig_m), use_container_width=True)
        ui.download_button(df_gm, f"Metas_{anio_sel}", "📥 Descargar Datos de Metas")

        st.divider()
        st.markdown(f"### 🗓️ Comparativo USD: {anio_sel} vs {anio_sel-1}")
        v_ant_g = df_ant.groupby('Mes_Num')['Venta_Neta_USD'].sum().reset_index().rename(columns={'Venta_Neta_USD': 'Anterior'})
        df_gc = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_ant_g, on='Mes_Num', how='left').fillna(0)
        df_gc['Mes'] = df_gc['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Actual'], name=f'{anio_sel}', marker_color='#2980b9', text=df_gc['Actual'], texttemplate='%{y:$.3s}', textposition='auto'))
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Anterior'], name=f'{anio_sel-1}', marker_color='#95a5a6', text=df_gc['Anterior'], texttemplate='%{y:$.3s}', textposition='auto'))
        st.plotly_chart(ui.config_plotly(fig_c), use_container_width=True)
        ui.download_button(df_gc, f"Comparativo_{anio_sel}_vs_{anio_sel-1}", "📥 Descargar Comparativo Anual")

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
            st.plotly_chart(ui.config_plotly(fig_w), use_container_width=True)
            ui.download_button(v_semana, "Ventas_Semana_Actual", "📥 Descargar Ventas Semana")
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
                
                st.plotly_chart(ui.config_plotly(fig_mix), use_container_width=True)
                ui.download_button(df_grp, f"Mix_Plan_{anio_sel}", "📥 Descargar Datos del Mix")
       
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
            st.plotly_chart(ui.config_plotly(go.Figure(go.Bar(x=r_fin.sort_values('Venta_Neta').tail(20)['Venta_Neta'], y=r_fin.sort_values('Venta_Neta').tail(20)['Vendedor'], orientation='h', text=r_fin.sort_values('Venta_Neta').tail(20)['T'], textposition='auto', marker_color='#2ecc71'))), use_container_width=True)
            ui.download_button(r_fin, "Ranking_Vendedores", "📥 Descargar Ranking")

# === PESTAÑA 2: PROYECTOS (ESTRUCTURA v10.7) ===
with tab_renta:
    df_pnl = services.cargar_pnl_historico()
    if not df_an.empty:
        with st.container(border=True):
            st.markdown("##### 🔍 Búsqueda de Proyecto")
            c1, c2 = st.columns(2)
            mapa_c = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Plan_Nombre']))
            mapa_n = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Cuenta_Nombre']))
            with c1: planes = st.multiselect("Filtrar por Plan (Opcional):", sorted(list(set(mapa_c.values()))))
            if planes:
                posibles = [id for id, p in mapa_c.items() if p in planes]
                nombres = [mapa_n[id] for id in posibles]
            else:
                nombres = list(mapa_n.values())
            with c2: proys = st.multiselect("Proyectos a Analizar:*", sorted(list(set(nombres))))
            
        if proys:
            sel_ids = [id for id, n in mapa_n.items() if n in proys]
            df_f = df_pnl[df_pnl['id_cuenta_analitica'].isin(sel_ids)] if not df_pnl.empty else pd.DataFrame()
            totales = {k: abs(df_f[df_f['Clasificacion']==k]['Monto_Neto'].sum()) if not df_f.empty else 0 
                      for k in ['Venta','Instalación','Suministros','WIP','Provisión','Costo Retail','Otros Gastos']}
            totales['Ajustes Inv'] = df_f[df_f['Clasificacion']=='Ajustes Inv']['Monto_Neto'].sum() if not df_f.empty else 0
            
            # Cargas Operativas
            df_h = services.cargar_detalle_horas_mes(sel_ids)
            df_s, _, bods = services.cargar_inventario_ubicacion_proyecto_v4(sel_ids, proys)
            df_c = services.cargar_compras_pendientes_v7_json_scanner(sel_ids, tc_usd)
            df_fe = services.cargar_facturacion_estimada_v2(sel_ids, tc_usd)
            
            # CALCULOS FINALES v10.7 (ALERTA OPERATIVA)
            # 1. Ingresos (Total Proyecto)
            total_fact = totales['Venta']
            total_pend = df_fe['Monto_CRC'].sum() if not df_fe.empty else 0
            total_ing = total_fact + total_pend
            
            # Filtrar df_h para solo sumar el costo del mes en curso (costo transitorio no reclasificado)
            hoy = datetime.now()
            df_h_mes = df_h[(pd.to_datetime(df_h['Fecha']).dt.year == hoy.year) & (pd.to_datetime(df_h['Fecha']).dt.month == hoy.month)] if not df_h.empty and 'Fecha' in df_h.columns else pd.DataFrame()
            costo_horas_mes = df_h_mes['Costo'].sum() if not df_h_mes.empty else 0
            
            # 2. Costo Vivo (TRANSITORIO + CONTABLE - PROVISIONES)
            # El usuario solicita incluir todos los costos y restar provisiones
            costo_vivo = (
                totales['Costo Retail'] + totales['Suministros'] + totales['Instalación'] + 
                totales['Ajustes Inv'] + totales['Otros Gastos'] + totales['WIP'] +
                (df_s['Valor_Total'].sum() if not df_s.empty else 0) + 
                (df_c['Monto_Pendiente'].sum() if not df_c.empty else 0) + 
                costo_horas_mes
            ) - totales['Provisión']
            
            # 3. Margen Actual (Ingreso Total - Costo Vivo Completo)
            margen_actual = total_ing - costo_vivo
            pct_actual = (margen_actual / total_ing * 100) if total_ing > 0 else 0
            
            color_alerta = "bg-alert-green" if pct_actual > 30 else ("bg-alert-warn" if pct_actual > 10 else "bg-alert-red")
        else:
            st.info("💡 Seleccione uno o más proyectos para visualizar la rentabilidad. Las tarjetas reaccionarán dinámicamente.")
            df_f = df_h = df_s = df_c = df_fe = pd.DataFrame()
            totales = {k: 0 for k in ['Venta','Instalación','Suministros','WIP','Provisión','Costo Retail','Otros Gastos', 'Ajustes Inv']}
            total_fact = total_pend = total_ing = costo_horas_mes = costo_vivo = margen_actual = pct_actual = 0
            color_alerta = "bg-alert-warn"

            st.markdown("#### 🚦 Semáforo de Rentabilidad Actual")
            st.caption("Margen calculado en tiempo real: (Total Ingresos - Todos los Costos). Se incluyen costos fijos, transitorios y se restan provisiones.")
            
            k1, k2, k3, k4 = st.columns(4)
            with k1: ui.card_kpi("Ingreso Total Proy.", total_ing, "border-green")
            with k2: ui.card_kpi("Costo Vivo Total", costo_vivo, "border-red")
            with k3: ui.card_kpi("MARGEN ACTUAL", margen_actual, color_alerta)
            with k4: ui.card_kpi("% Actual", pct_actual, "border-blue", formato="percent")
            
            st.divider()
            
            st.markdown("#### 📊 Desglose de Componentes del Proyecto")
            
            # Fila 1
            c1, c2, c3, c4 = st.columns(4)
            with c1: ui.card_kpi("Facturado (Real)", total_fact, "border-green", "Ingreso")
            with c2: ui.card_kpi("Por Facturar", total_pend, "border-green", "Ingreso")
            with c3: ui.card_kpi("Instalación", totales['Instalación'], "border-red", "Firme")
            with c4: ui.card_kpi("Suministros", totales['Suministros'], "border-red", "Firme")
            
            # Fila 2
            c5, c6, c7, c8 = st.columns(4)
            with c5: ui.card_kpi("Costo Venta", totales['Costo Retail'], "border-red", "Firme")
            with c6: ui.card_kpi("Ajustes Inv.", totales['Ajustes Inv'], "border-red", "Firme")
            with c7: ui.card_kpi("Otros Gastos", totales['Otros Gastos'], "border-red", "Firme")
            with c8: ui.card_kpi("Inventario Sitio", df_s['Valor_Total'].sum() if not df_s.empty else 0, "border-blue", "Transitorio")
            
            # Fila 3
            c9, c10, c11, c12 = st.columns(4)
            with c9: ui.card_kpi("WIP (En Proceso)", totales['WIP'], "border-blue", "Transitorio")
            with c10: ui.card_kpi("Compras Pend.", df_c['Monto_Pendiente'].sum() if not df_c.empty else 0, "border-blue", "Transitorio")
            with c11: ui.card_kpi("Horas Depto", costo_horas_mes, "border-blue", "Mes Actual (Trans.)")
            with c12: ui.card_kpi("Provisiones", totales['Provisión'], "border-gray", "Aviso (No suma)") 
            
        if proys:
            st.divider()
            t1, t2, t3, t4, t5, t6 = st.tabs(["Inventario", "Compras", "Contabilidad", "Fact. Pend.", "Historial Inv.", "Parte de Horas"])
            with t1: 
                st.dataframe(df_s, use_container_width=True)
                ui.download_button(df_s, "Inventario_en_Sitio", "📥 Descargar Inventario")
            with t2: 
                st.dataframe(df_c, use_container_width=True)
                ui.download_button(df_c, "Compras_Pendientes_Proyecto", "📥 Descargar Compras")
            with t3: 
                if not df_f.empty:
                    cols_contables = ['Fecha', 'Descripción de Asiento', 'Proveedor o Cliente', 'Debe', 'Haber', 'Clasificacion']
                    cols_disp = [c for c in cols_contables if c in df_f.columns]
                    st.dataframe(df_f[cols_disp], use_container_width=True, hide_index=True)
                else:
                    st.dataframe(df_f, use_container_width=True)
                ui.download_button(df_f, "Contabilidad_Proyecto", "📥 Descargar Contabilidad")
            with t4: 
                st.dataframe(df_fe, use_container_width=True)
                ui.download_button(df_fe, "Facturacion_Pendiente", "📥 Descargar Facturacion")
            with t5:
                df_ensambles, df_cust, df_post, hist_status = services.cargar_historial_inventario_proyecto(sel_ids, proys)
                
                if df_ensambles.empty and df_cust.empty and df_post.empty:
                    st.info(f"No hay historial registrable o status: {hist_status}")
                
                st.subheader("🛠️ Ensambles (Producción)")
                if not df_ensambles.empty:
                    df_to_show_p = df_ensambles[['Producto', 'Ensamblado_OUT', 'Desensamblado_IN', 'Neto_Ensamblado']].rename(columns={
                        'Ensamblado_OUT': 'Ensamblado',
                        'Desensamblado_IN': 'Desensamblado',
                        'Neto_Ensamblado': 'Neto Ensamblado'
                    })
                    
                    def highlight_110(row):
                        if str(row['Producto']).startswith('[110'):
                            return ['color: lightblue']*len(row)
                        else:
                            return ['']*len(row)
                            
                    styled_df_p = df_to_show_p.style.apply(highlight_110, axis=1)
                    
                    st.dataframe(styled_df_p, use_container_width=True)
                    st.download_button("📥 Descargar Ensambles", data=ui.convert_df_to_excel(df_ensambles), file_name=f"Ensambles_{proys[0][:10]}.xlsx", key=f"dwn_prod_{proys[0]}")
                else:
                    st.info("No hay historial de ensambles registrable.")
                
                st.divider()
                
                st.subheader("🚚 Entregas (Cliente)")
                if not df_cust.empty:
                    df_to_show_c = df_cust[['Producto', 'Entregado_OUT', 'Devuelto_IN', 'Neto_Entregado']].rename(columns={
                        'Entregado_OUT': 'Entregado a Cliente',
                        'Devuelto_IN': 'Devuelto por Cliente',
                        'Neto_Entregado': 'Neto Entregado'
                    })
                    
                    st.dataframe(df_to_show_c, use_container_width=True)
                    st.download_button("📥 Descargar Entregas", data=ui.convert_df_to_excel(df_cust), file_name=f"Entregas_{proys[0][:10]}.xlsx", key=f"dwn_cust_{proys[0]}")
                else:
                    st.info("No hay historial de entregas al cliente registrable.")
                    
                st.divider()
                
                st.subheader("🔧 Ajustes Posteriores")
                if not df_post.empty:
                    df_to_show_post = df_post[['Producto', 'Ajuste_IN', 'Ajuste_OUT', 'Neto_Ajuste']].rename(columns={
                        'Ajuste_IN': 'Ingreso p/Ajuste',
                        'Ajuste_OUT': 'Salida p/Ajuste',
                        'Neto_Ajuste': 'Ajuste Neto'
                    })
                    
                    st.dataframe(df_to_show_post, use_container_width=True)
                    st.download_button("📥 Descargar Ajustes", data=ui.convert_df_to_excel(df_post), file_name=f"Ajustes_{proys[0][:10]}.xlsx", key=f"dwn_post_{proys[0]}")
                else:
                    st.info("No hay ajustes posteriores registrables.")
                
            with t6:
                if not df_h.empty:
                    cols_horas = ['Fecha', 'Técnico', 'Tipo_Hora', 'Horas']
                    df_h_show = df_h[[c for c in cols_horas if c in df_h.columns]].rename(columns={'Tipo_Hora': 'Tipo de Hora', 'Horas': 'Cantidad (Horas)'})
                    st.dataframe(df_h_show, use_container_width=True, hide_index=True)
                    ui.download_button(df_h_show, "Parte_de_Horas", "📥 Descargar Horas")
                else:
                    st.info("No hay registro de horas para este proyecto.")
                    
            st.divider()

            # --- ESTADO DE RESULTADOS (V3: CON COMISIÓN VENDEDOR) ---
            
            # 1. Valores Iniciales
            kilometraje_inicial = 0 
            
            # 2. Construir DataFrame con Fórmulas
            data_pnl = [
                # FILA 2: Ingresos
                {"Concepto": "INGRESOS (Facturado Real)", "Monto": total_fact, "Notas": "Dato Fijo (Sistema)"},
                
                # FILAS 3-7: Costos Sistema
                {"Concepto": "(-) Costo de Venta", "Monto": totales['Costo Retail'], "Notas": "Dato Fijo (Sistema)"},
                {"Concepto": "(-) Costo Instalación", "Monto": totales['Instalación'], "Notas": "Dato Fijo (Sistema)"},
                {"Concepto": "(-) Costo Suministros", "Monto": totales['Suministros'], "Notas": "Dato Fijo (Sistema)"},
                {"Concepto": "(-) Ajustes de Inventario", "Monto": totales['Ajustes Inv'], "Notas": "Dato Fijo (Sistema)"},
                {"Concepto": "(-) Otros Gastos", "Monto": totales['Otros Gastos'], "Notas": "Dato Fijo (Sistema)"},
                
                # FILA 8: Manual (Km)
                {"Concepto": "(-) KILOMETRAJE", "Monto": kilometraje_inicial, "Notas": "MANUAL (Editar en Excel)"},
                
                # FILA 9: Separador
                {"Concepto": "--------------------------------", "Monto": None, "Notas": ""},
                
                # FILA 10: Utilidad Operativa (=B2-SUM(B3:B8))
                {"Concepto": "(=) UTILIDAD OPERATIVA", "Monto": "=B2-SUM(B3:B8)", "Notas": "Calculado (Fórmula)"},
                
                # FILA 11: Margen Operativo (=B10/B2)
                {"Concepto": "(%) MARGEN OPERATIVO", "Monto": "=IF(B2<>0, B10/B2, 0)", "Notas": "Calculado (Fórmula)"},
                
                # FILA 12: Espacio
                {"Concepto": "", "Monto": None, "Notas": ""},
                
                # FILA 13: Gasto Admin % (Manual)
                {"Concepto": "(-) GASTO ADMINISTRATIVO (%)", "Monto": 0, "Notas": "MANUAL (Poner % ej: 10%)"},
                
                # FILA 14: Gasto Admin Monto (=B10*B13)
                {"Concepto": "(-) Gasto Administrativo (Monto)", "Monto": "=B10*B13", "Notas": "Calculado (Fórmula)"},
                
                # FILA 15: Utilidad Final (=B10-B14)
                {"Concepto": "(=) UTILIDAD FINAL", "Monto": "=B10-B14", "Notas": "Calculado (Fórmula)"},
                
                # FILA 16: Margen Real Final (=B15/B2)
                {"Concepto": "(%) MARGEN REAL FINAL", "Monto": "=IF(B2<>0, B15/B2, 0)", "Notas": "Calculado (Fórmula)"},
                
                # --- NUEVA FILA 17: COMISIÓN VENDEDOR ---
                # Regla: >=35% -> 12% Utilidad | >=8% -> 10% Utilidad | <8% -> 0
                {"Concepto": "($) COMISIÓN VENDEDOR", "Monto": "=IF(B16>=0.35, B15*0.12, IF(B16>=0.08, B15*0.10, 0))", "Notas": "Calculado (Regla Margen)"}
            ]
            
            df_pnl_rep = pd.DataFrame(data_pnl)

            # 3. Generar Excel
            buffer_proy = io.BytesIO()
            with pd.ExcelWriter(buffer_proy, engine='openpyxl') as writer:
                # Hoja Principal
                df_pnl_rep.to_excel(writer, sheet_name='Estado_Resultados', index=False)
                
                # --- FORMATOS ---
                ws = writer.sheets['Estado_Resultados']
                
                # Porcentajes (B11, B13, B16)
                for celda in ['B11', 'B13', 'B16']:
                    ws[celda].number_format = '0.00%'
                
                # Moneda (B2-B10, B14-B15 y B17)
                for i in range(2, 11): 
                    ws[f'B{i}'].number_format = '#,##0.00'
                ws['B14'].number_format = '#,##0.00'
                ws['B15'].number_format = '#,##0.00'
                ws['B17'].number_format = '#,##0.00' # Nueva celda Comisión
                
                # Estilo Visual (Ancho de columnas)
                ws.column_dimensions['A'].width = 35
                ws.column_dimensions['B'].width = 18
                
                # Hojas de Soporte
                resumen_kpi = pd.DataFrame({
                    'Concepto': ['Ingreso Total Proyecto', 'Costo Vivo Total', 'Margen Actual'],
                    'Monto': [total_ing, costo_vivo, margen_actual]
                })
                resumen_kpi.to_excel(writer, sheet_name='Datos_Tablero', index=False)
                
                if not df_s.empty: df_s.to_excel(writer, sheet_name='Detalle_Inventario', index=False)
                if not df_c.empty: df_c.to_excel(writer, sheet_name='Compras_Pendientes', index=False)
                if not df_f.empty: df_f.to_excel(writer, sheet_name='Contabilidad_Full', index=False)
            
            st.download_button(
                f"📥 Descargar ER con Comisión: {', '.join(proys[:1])}...", 
                data=buffer_proy.getvalue(), 
                file_name=f"ER_{proys[0][:10]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
# === PESTAÑA 3: PRODUCTOS (ACTUALIZADA: Métrica + Cat + Zona + Vendedor) ===
with tab_prod:
    df_cat = services.cargar_inventario_general()
    if not df_prod.empty:
        # --- 1. FILTROS GENERALES ---
        c_f1, c_f2 = st.columns([1, 4])
        with c_f1: 
            anio = st.selectbox("📅 Año", sorted(df_prod['date'].dt.year.unique(), reverse=True), key="prod_anio_sel")
        with c_f2: 
            # Selector de métrica (Afecta a TODOS los gráficos)
            tipo_ver = st.radio("📊 Ver Gráficos por:", 
                                ["Monto (₡)", "Cantidad (Und)", "Freq. Facturas (# Docs)"], 
                                index=0, horizontal=True, key="prod_metric_sel")
        
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
        
        # Mix por Tipo (Con altura ajustada y padding)
        grp_tipo = df_p.groupby('Tipo')[col_calc].agg(agg_func).reset_index()
        with c_m1: 
            fig_pie = px.pie(grp_tipo, values=col_calc, names='Tipo', 
                             title=f"Mix por Tipo ({tipo_ver})", 
                             height=300)
            fig_pie.update_layout(title_pad=dict(b=20), margin=dict(t=50, b=10, l=10, r=10))
            st.plotly_chart(ui.config_plotly(fig_pie), use_container_width=True)
            ui.download_button(grp_tipo, "Mix_Tipo_Producto")
        
        # Top 10 Global
        grp_top_full = df_p.groupby('Producto')[col_calc].agg(agg_func).sort_values(ascending=False).reset_index()
        grp_top_show = grp_top_full.head(10).sort_values(col_calc) # Volvemos a ordenar para que tail/head se vea bien en H bar
        with c_m2: 
            st.plotly_chart(ui.config_plotly(px.bar(grp_top_show, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, title=f"Top 10 Global ({tipo_ver})")), use_container_width=True)
            ui.download_button(grp_top_full, "Listado_Productos_Global")

        # --- PREPARACIÓN DE DATOS DETALLADOS ---
        if not df_main.empty:
            # ACTUALIZACIÓN: Ahora traemos también 'Vendedor' en el merge
            df_merged = pd.merge(df_p, df_main[['id', 'Categoria_Cliente', 'Zona_Comercial', 'Vendedor']], left_on='ID_Factura', right_on='id', how='left')
            df_merged['Categoria_Cliente'] = df_merged['Categoria_Cliente'].fillna("Sin Categoría")
            df_merged['Zona_Comercial'] = df_merged['Zona_Comercial'].fillna("Sin Zona")
            df_merged['Vendedor'] = df_merged['Vendedor'].fillna("Sin Asignar")

            st.divider()
            
            # --- 3. POR CATEGORÍA DE CLIENTE ---
            c_cat1, c_cat2 = st.columns([1, 3])
            with c_cat1: 
                st.subheader(f"🛍️ Por Categoría")
                cats = sorted(df_merged['Categoria_Cliente'].unique())
                cat_sel = st.selectbox("Filtrar Categoría:", cats, key="prod_cat_filter")
            
            with c_cat2:
                df_cf = df_merged[df_merged['Categoria_Cliente'] == cat_sel]
                df_cf_full = df_cf.groupby('Producto')[col_calc].agg(agg_func).sort_values(ascending=False).reset_index()
                if not df_cf_full.empty:
                    top_cat_show = df_cf_full.head(10).sort_values(col_calc)
                    fig_cat = px.bar(top_cat_show, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {cat_sel}", color_discrete_sequence=['#8e44ad'])
                    st.plotly_chart(ui.config_plotly(fig_cat), use_container_width=True)
                    ui.download_button(df_cf_full, f"Productos_{cat_sel}")
                else:
                    st.info("Sin datos.")

            st.divider()

            # --- 4. POR ZONA COMERCIAL ---
            c_zon1, c_zon2 = st.columns([1, 3])
            with c_zon1: 
                st.subheader(f"🌍 Por Zona")
                zonas = sorted(df_merged['Zona_Comercial'].unique())
                zona_sel = st.selectbox("Filtrar Zona:", zonas, key="prod_zona_filter")
            
            with c_zon2:
                df_zf = df_merged[df_merged['Zona_Comercial'] == zona_sel]
                df_zf_full = df_zf.groupby('Producto')[col_calc].agg(agg_func).sort_values(ascending=False).reset_index()
                if not df_zf_full.empty:
                    top_zona_show = df_zf_full.head(10).sort_values(col_calc)
                    fig_zona = px.bar(top_zona_show, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {zona_sel}", color_discrete_sequence=['#16a085'])
                    st.plotly_chart(ui.config_plotly(fig_zona), use_container_width=True)
                    ui.download_button(df_zf_full, f"Productos_{zona_sel}")
                else:
                    st.info("Sin datos.")

            st.divider()

            # --- 5. POR VENDEDOR (NUEVO) ---
            c_ven1, c_ven2 = st.columns([1, 3])
            with c_ven1: 
                st.subheader(f"👤 Por Vendedor")
                vendedores = sorted(df_merged['Vendedor'].unique())
                vend_sel = st.selectbox("Filtrar Vendedor:", vendedores, key="prod_vend_filter")
            
            with c_ven2:
                df_vf = df_merged[df_merged['Vendedor'] == vend_sel]
                df_vf_full = df_vf.groupby('Producto')[col_calc].agg(agg_func).sort_values(ascending=False).reset_index()
                if not df_vf_full.empty:
                    top_vend_show = df_vf_full.head(10).sort_values(col_calc)
                    fig_vend = px.bar(top_vend_show, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {vend_sel}", color_discrete_sequence=['#d35400'])
                    st.plotly_chart(ui.config_plotly(fig_vend), use_container_width=True)
                    ui.download_button(df_vf_full, f"Productos_Vendedor_{vend_sel}")
                else:
                    st.info("Sin datos.")
            
            
            # --- 6. ANÁLISIS DE RENTABILIDAD (NUEVO) ---
            # (Deshabilitado por solicitud del usuario)

# === PESTAÑA 4: BAJA ROTACIÓN ===
with tab_inv:
    if st.button("🔄 Calcular Rotación"):
        df_h, status = services.cargar_inventario_baja_rotacion()
        if not df_h.empty:
            days = st.slider("Días Inactivo:", 0, 720, 365)
            df_show = df_h[df_h['Dias_Sin_Salida'] >= days]
            c1, c2, c3 = st.columns(3)
            with c1: ui.card_kpi("Capital Estancado", df_show['Valor'].sum(), "border-red")
            with c2: ui.card_kpi("Total Items", len(df_h), "border-gray", formato="numero")
            with c3: ui.card_kpi("Items Críticos", len(df_show), "border-orange", formato="numero")
            st.dataframe(df_show[['Producto','Ubicacion','quantity','Dias_Sin_Salida','Valor']], use_container_width=True)
            ui.download_button(df_show, "Inventario_Baja_Rotacion", "📥 Descargar Inventario Inactivo")
        else: st.info(status)

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    df_cx = services.cargar_cartera()
    if not df_cx.empty:
        deuda = df_cx['amount_residual'].sum()
        vencido = df_cx[df_cx['Dias_Vencido']>0]['amount_residual'].sum()
        c1, c2, c3 = st.columns(3)
        with c1: ui.card_kpi("Por Cobrar", deuda, "border-blue")
        with c2: ui.card_kpi("Vencido", vencido, "border-red")
        with c3: ui.card_kpi("Salud", f"{(1-(vencido/deuda))*100:.1f}% al día" if deuda>0 else "100%", "border-green", formato="raw")
        c_g, c_t = st.columns([2,1])
        with c_g:
            df_b = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            st.plotly_chart(ui.config_plotly(px.bar(df_b, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad')), use_container_width=True)
            ui.download_button(df_b, "Antiguedad_Cartera")
        with c_t:
            df_full_deuda = df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).reset_index()
            st.dataframe(df_full_deuda.head(15), use_container_width=True)
            ui.download_button(df_full_deuda, "Deuda_Cartera_Completa", "📥 Descargar Cartera Completa")

# === PESTAÑA 6: SEGMENTACIÓN ===
with tab_cli:
    if not df_main.empty:
        anio_c = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sc")
        df_c = df_main[df_main['invoice_date'].dt.year == anio_c]
        c1, c2, c3 = st.columns(3)
        with c1: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Provincia', 'Ventas por Provincia', prefix="₡")), use_container_width=True)
            ui.download_button(df_c.groupby('Provincia')['Venta_Neta'].sum().reset_index(), f"Ventas_Provincia_{anio_c}")
        with c2: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Zona_Comercial', 'Ventas por Zona', prefix="₡")), use_container_width=True)
            ui.download_button(df_c.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index(), f"Ventas_Zona_{anio_c}")
        with c3: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Categoria_Cliente', 'Ventas por Categoría', prefix="₡")), use_container_width=True)
            ui.download_button(df_c.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), f"Ventas_Categoria_{anio_c}")
        st.divider()
        df_old = df_main[df_main['invoice_date'].dt.year == (anio_c - 1)]
        cli_now = set(df_c['Cliente'])
        cli_old = set(df_old['Cliente'])
        nuevos = list(cli_now - cli_old)
        perdidos = list(cli_old - cli_now)
        k1, k2, k3, k4 = st.columns(4)
        with k1: ui.card_kpi("Activos", len(cli_now), "border-blue", formato="numero")
        with k2: ui.card_kpi("Nuevos", len(nuevos), "border-green", formato="numero")
        with k3: ui.card_kpi("Churn", len(perdidos), "border-red", formato="numero")
        with k4: ui.card_kpi("Retención", f"{len(cli_old.intersection(cli_now))/len(cli_old)*100:.1f}%" if cli_old else "100%", "border-purple", formato="raw")
        c_top, c_lost = st.columns(2)
        with c_top:
            st.subheader("Top Clientes")
            df_top_clis_full = df_c.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
            df_top_clis_show = df_top_clis_full.head(10).sort_values('Venta_Neta')
            st.plotly_chart(ui.config_plotly(px.bar(df_top_clis_show, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
            ui.download_button(df_top_clis_full, f"Listado_Clientes_{anio_c}")
        with c_lost:
            st.subheader("Oportunidad (Perdidos)")
            if perdidos:
                df_l_full = df_old[df_old['Cliente'].isin(perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
                df_l_show = df_l_full.head(10).sort_values('Venta_Neta')
                st.plotly_chart(ui.config_plotly(px.bar(df_l_show, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)
                ui.download_button(df_l_full, f"Clientes_Perdidos_Full_{anio_c}")

        st.divider()
        
        # --- ANÁLISIS DE RIESGO (NUEVO) ---
        st.subheader("🚨 Clientes en Riesgo (Alerta Temprana)")
        st.caption("Clientes activos que han superado en 1.5x su ciclo habitual de compra.")
        
        # 1. Calcular frecuencia por cliente
        df_risk = df_main.sort_values(['Cliente', 'invoice_date'])
        df_risk['Prev_Date'] = df_risk.groupby('Cliente')['invoice_date'].shift(1)
        df_risk['Days_Diff'] = (df_risk['invoice_date'] - df_risk['Prev_Date']).dt.days
        
        # Promedio histórico por cliente
        freq_cli = df_risk.groupby('Cliente')['Days_Diff'].mean().reset_index().rename(columns={'Days_Diff': 'Ciclo_Habitual'})
        
        # Última compra
        last_buy = df_risk.groupby('Cliente')['invoice_date'].max().reset_index().rename(columns={'invoice_date': 'Ultima_Compra'})
        
        # Unir
        df_alerta = pd.merge(freq_cli, last_buy, on='Cliente')
        df_alerta['Dias_Sin_Comprar'] = (datetime.now() - df_alerta['Ultima_Compra']).dt.days
        
        # Lógica de Riesgo: (Días > Ciclo*1.5) Y (Días < 365) [No perdidos aún] Y (Ciclo > 0)
        df_alerta['Alerta'] = (df_alerta['Dias_Sin_Comprar'] > (df_alerta['Ciclo_Habitual'] * 1.5)) & \
                              (df_alerta['Dias_Sin_Comprar'] < 365) & \
                              (df_alerta['Ciclo_Habitual'] > 0)
                              
        alertas = df_alerta[df_alerta['Alerta']].sort_values('Venta_Neta', ascending=False) if 'Venta_Neta' in df_alerta.columns else df_alerta[df_alerta['Alerta']].copy() 
        # (Nota: Venta_Neta no está en df_alerta, hay que unirla si queremos ordenar por importancia)
        
        # Traer Venta Total Histórica para ordenar
        vta_hist = df_main.groupby('Cliente')['Venta_Neta'].sum().reset_index()
        alertas = pd.merge(alertas, vta_hist, on='Cliente', how='left').sort_values('Venta_Neta', ascending=False)
        
        if not alertas.empty:
            c_r1, c_r2 = st.columns([1,3])
            with c_r1:
                ui.card_kpi("Clientes en Riesgo", len(alertas), "bg-alert-warn", formato="numero")
                
            with c_r2: 
                # Mostrar tabla simplificada
                st.dataframe(
                    alertas[['Cliente', 'Ciclo_Habitual', 'Dias_Sin_Comprar', 'Venta_Neta']].style.format({
                        'Ciclo_Habitual': '{:.0f} días',
                        'Dias_Sin_Comprar': '{:.0f} días',
                        'Venta_Neta': '₡{:,.0f}'
                    }), use_container_width=True, height=300
                )
                ui.download_button(alertas[['Cliente', 'Ciclo_Habitual', 'Dias_Sin_Comprar', 'Venta_Neta']], "Clientes_en_Riesgo")
        else:
            st.success("✅ No se detectan clientes en riesgo de fuga inminente basado en sus ciclos de compra.")

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        with c1: anio_v = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sv")
        with c2: 
            mes_nombres = {0: "Todos", 1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                           7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            mes_v_nom = st.selectbox("Mes", list(mes_nombres.values()), key="smv")
            mes_v = [k for k, v in mes_nombres.items() if v == mes_v_nom][0]
        with c3: vend = st.selectbox("Vendedor", sorted(df_main['Vendedor'].unique()))
        
        # Filtrado base por Año y Vendedor
        df_v = df_main[(df_main['invoice_date'].dt.year == anio_v) & (df_main['Vendedor'] == vend)]
        df_v_old = df_main[(df_main['invoice_date'].dt.year == (anio_v-1)) & (df_main['Vendedor'] == vend)]
        
        # Filtrado por Mes (si no es Todos)
        if mes_v > 0:
            df_v = df_v[df_v['invoice_date'].dt.month == mes_v]
            df_v_old = df_v_old[df_v_old['invoice_date'].dt.month == mes_v]
            
        perdidos_v = list(set(df_v_old['Cliente']) - set(df_v['Cliente']))
        
        # Cálculos de KPIs adicionales
        venta_act = df_v['Venta_Neta'].sum()
        venta_ant = df_v_old['Venta_Neta'].sum()
        delta_v = (venta_act - venta_ant) / venta_ant * 100 if venta_ant > 0 else 0
        
        ticket_prom = venta_act / df_v['name'].nunique() if df_v['name'].nunique() > 0 else 0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: ui.card_kpi("Venta", venta_act, "border-green", nota=f"{delta_v:+.1f}% vs Año Ant." if venta_ant > 0 else "Sin datos prev.")
        with k2: ui.card_kpi("Ticket Promedio", ticket_prom, "border-purple", nota="Monto prom. p/factura")
        with k3: ui.card_kpi("Clientes", df_v['Cliente'].nunique(), "border-blue", formato="numero")
        with k4: ui.card_kpi("Riesgo", len(perdidos_v), "border-red", formato="numero")
        c_v1, c_v2 = st.columns(2)
        with c_v1:
            st.subheader("Mejores Clientes")
            if not df_v.empty:
                df_best_full = df_v.groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
                df_best_show = df_best_full.head(10).sort_values('Venta_Neta')
                st.plotly_chart(ui.config_plotly(px.bar(df_best_show, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
                ui.download_button(df_best_full, f"Ventas_por_Cliente_{vend}")
        with c_v2:
            st.subheader("Cartera Perdida")
            if perdidos_v:
                df_lst_full = df_v_old[df_v_old['Cliente'].isin(perdidos_v)].groupby('Cliente')['Venta_Neta'].sum().sort_values(ascending=False).reset_index()
                df_lst_show = df_lst_full.head(10).sort_values('Venta_Neta')
                st.plotly_chart(ui.config_plotly(px.bar(df_lst_show, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)
                ui.download_button(df_lst_full, f"Cartera_Perdida_Full_{vend}")

        st.divider()
        
        st.divider()
        
        # Filtrar productos correspondientes a las facturas del vendedor seleccionado
        if not df_v.empty and not df_prod.empty:
            ids_facturas_vendedor = df_v['id'].unique()
            df_prod_vend = df_prod[df_prod['ID_Factura'].isin(ids_facturas_vendedor)]
            
            if not df_prod_vend.empty:
                # --- SELECTOR DE MÉTRICA ---
                c_sel1, c_sel2 = st.columns([1, 3])
                with c_sel1:
                    metrica_vend = st.radio("Ver por:", ["Monto (₡)", "Cantidad (Und)", "Freq. (Docs)"], horizontal=True, label_visibility="collapsed")
                
                # Config métrica
                if "Monto" in metrica_vend: val_col, agg, fmt = 'Venta_Neta', 'sum', '.2s'
                elif "Cantidad" in metrica_vend: val_col, agg, fmt = 'quantity', 'sum', '.2s'
                else: val_col, agg, fmt = 'ID_Factura', 'nunique', ''
                
                c_top10, c_brand = st.columns(2)
                
                with c_top10:
                    st.subheader(f"🏆 Top 10 Productos ({metrica_vend})")
                    prods_full = df_prod_vend.groupby('Producto')[val_col].agg(agg).sort_values(ascending=False).reset_index()
                    prods_show = prods_full.head(10).sort_values(val_col)
                    fig_vp = px.bar(prods_show, x=val_col, y='Producto', orientation='h', text_auto=fmt, 
                                    title=f"Top Productos")
                    fig_vp.update_traces(marker_color='#27ae60')
                    st.plotly_chart(ui.config_plotly(fig_vp), use_container_width=True)
                    ui.download_button(prods_full, f"Listado_Productos_{vend}")
                
                with c_brand:
                    st.subheader(f"🥧 Mix por Marca ({metrica_vend})")
                    # Traer datos de marca desde inventario
                    df_inv = services.cargar_inventario_general()
                    if not df_inv.empty and 'Marca' in df_inv.columns:
                        df_merged_brand = pd.merge(df_prod_vend, df_inv[['ID_Producto', 'Marca']], on='ID_Producto', how='left')
                        df_merged_brand['Marca'] = df_merged_brand['Marca'].fillna("Sin Marca")
                        
                        # Preparar datos para el pie chart usando la métrica seleccionada
                        df_pie_data = df_merged_brand.groupby('Marca')[val_col].agg(agg).reset_index()
                        
                        # Determinar prefijos/sufijos según métrica
                        pre = "₡" if "Monto" in metrica_vend else ""
                        suf = " Und" if "Cantidad" in metrica_vend else (" Docs" if "Freq" in metrica_vend else "")

                        # Usar el helper con parámetros de leyenda
                        fig_brand = create_improved_pie(df_pie_data, val_col, 'Marca', "", prefix=pre, suffix=suf)
                        # Sobrescribir legend de ui.config_plotly para mantenerla vertical como pidió el usuario
                        fig_brand = ui.config_plotly(fig_brand)
                        fig_brand.update_layout(legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05))
                        st.plotly_chart(fig_brand, use_container_width=True)
                        ui.download_button(df_pie_data, f"Mix_Marca_{vend}")
                    else:
                        st.warning("No se pudo cargar información de Marcas.")
            else:
                st.info("No hay detalle de productos disponible para este vendedor.")

            st.divider()
            
            # --- NUEVA FILA: TENDENCIA Y CATEGORÍA ---
            c_trend, c_cat_v = st.columns(2)
            
            with c_trend:
                st.subheader("📈 Tendencia Mensual (YoY)")
                # Data Anual completa para el vendedor (sin filtro de mes para ver la tendencia)
                df_v_ann = df_main[(df_main['invoice_date'].dt.year == anio_v) & (df_main['Vendedor'] == vend)]
                df_v_old_ann = df_main[(df_main['invoice_date'].dt.year == (anio_v-1)) & (df_main['Vendedor'] == vend)]
                
                v_act_m = df_v_ann.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': str(anio_v)})
                v_ant_m = df_v_old_ann.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': str(anio_v-1)})
                
                df_trend_all = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act_m, on='Mes_Num', how='left').merge(v_ant_m, on='Mes_Num', how='left').fillna(0)
                df_trend_all['Mes'] = df_trend_all['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
                
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(x=df_trend_all['Mes'], y=df_trend_all[str(anio_v)], name=f"Año {anio_v}", line=dict(color='#2ecc71', width=3), mode='lines+markers'))
                fig_trend.add_trace(go.Scatter(x=df_trend_all['Mes'], y=df_trend_all[str(anio_v-1)], name=f"Año {anio_v-1}", line=dict(color='#95a5a6', dash='dash'), mode='lines+markers'))
                
                fig_trend.update_layout(height=350, margin=dict(t=30, b=30))
                st.plotly_chart(ui.config_plotly(fig_trend), use_container_width=True)
                ui.download_button(df_trend_all, f"Trend_YoY_{vend}")
                
            with c_cat_v:
                st.subheader("👥 Mix por Categoría de Cliente")
                if not df_v.empty:
                    fig_cat_v = create_improved_pie(df_v, 'Venta_Neta', 'Categoria_Cliente', "", prefix="₡")
                    fig_cat_v = ui.config_plotly(fig_cat_v)
                    fig_cat_v.update_layout(legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05))
                    st.plotly_chart(fig_cat_v, use_container_width=True)
                    ui.download_button(df_v.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), f"Mix_Cat_{vend}")
                else:
                    st.info("Sin datos de clientes para este periodo.")


# === PESTAÑA 8: RADIOGRAFÍA ===
with tab_det:
    if not df_main.empty:
        c_search, c_year = st.columns([3, 1])
        with c_search:
            cli = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()), index=None, placeholder="Escriba para buscar...")
        
        if cli:
            # Obtener años disponibles para este cliente
            df_full_history = df_main[df_main['Cliente'] == cli]
            available_years = sorted(df_full_history['invoice_date'].dt.year.unique(), reverse=True)
            
            with c_year:
                # Selector de Año (con opción 'Todos')
                rad_year = st.selectbox("Año:", ["Todos"] + available_years, key=f"rad_year_{cli}")
            
            # Filtrar datos según selección
            if rad_year == "Todos":
                df_cl = df_full_history
                is_filtered = False
            else:
                df_cl = df_full_history[df_full_history['invoice_date'].dt.year == rad_year]
                is_filtered = True

            # Cálculos KPI (Sobre la data filtrada)
            if not df_cl.empty:
                ultima = df_cl['invoice_date'].max()
                dias = (datetime.now() - ultima).days
                
                # KPI Crédito (Promedio general, no varía mucho por año pero lo recalculamos)
                dias_credito = df_cl['Dias_Credito'].mean() if 'Dias_Credito' in df_cl.columns else 0
                
                k1, k2, k3, k4, k5 = st.columns(5)
                with k1: ui.card_kpi(f"Venta {'Total' if not is_filtered else rad_year}", df_cl['Venta_Neta'].sum(), "border-green")
                with k2: ui.card_kpi("Última Compra", ultima.strftime('%d-%m-%Y'), "border-blue", formato="raw")
                with k3: ui.card_kpi("Días Inactivo", dias, "border-red" if dias>90 else "border-gray", formato="numero")
                with k4: ui.card_kpi("Días Crédito Prom.", dias_credito, "border-orange", formato="numero")
                with k5: ui.card_kpi("Ubicación", df_cl.iloc[0]['Provincia'], "border-purple", formato="raw")
                
                c_h, c_p = st.columns(2)
                with c_h:
                    st.subheader("Historial")
                    if is_filtered:
                        # Vista Mensual (Año seleccionado)
                        hist = df_cl.groupby(df_cl['invoice_date'].dt.month)['Venta_Neta'].sum().reset_index()
                        # Mapear número de mes a nombre
                        hist['Mes'] = hist['invoice_date'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',
                                                              7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
                        fig_h = px.bar(hist, x='Mes', y='Venta_Neta', text_auto='.2s', title=f"Ventas Mensuales {rad_year}")
                    else:
                        # Vista Anual (Historico Completo)
                        hist = df_cl.groupby(df_cl['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                        fig_h = px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s', title="Tendencia Anual")
                        fig_h.update_xaxes(type='category') # Asegurar que años se vean como categorías
                    
                    st.plotly_chart(ui.config_plotly(fig_h), use_container_width=True)

                with c_p:
                    c_head, c_sel = st.columns([1,1])
                    with c_head: st.subheader(f"Top Productos")
                    
                    # Selector Métrica Radiografía
                    with c_sel:
                        metrica_rad = st.radio("M:", ["Monto", "Cant.", "Freq."], horizontal=True, label_visibility="collapsed", key=f"rad_met_{cli}")
                    
                    if "Monto" in metrica_rad: r_val, r_agg, r_fmt = 'Venta_Neta', 'sum', '.2s'
                    elif "Cant" in metrica_rad: r_val, r_agg, r_fmt = 'quantity', 'sum', '.2s'
                    else: r_val, r_agg, r_fmt = 'ID_Factura', 'nunique', ''

                    if not df_prod.empty:
                        # Filtrar productos usando las facturas del cliente filtrado
                        df_cp = df_prod[df_prod['ID_Factura'].isin(df_cl['id'])]
                        if not df_cp.empty:
                            top = df_cp.groupby('Producto')[r_val].agg(r_agg).sort_values(ascending=True).tail(10).reset_index()
                            st.plotly_chart(ui.config_plotly(px.bar(top, x=r_val, y='Producto', orientation='h', text_auto=r_fmt)), use_container_width=True)
                        else:
                            st.info("No hay productos para este rango.")
            else:
                 st.info(f"No hay registros de ventas para el año {rad_year}.")
                
# ... (después de mostrar los gráficos del cliente) ...              
# PREPARAR DESCARGA DEL CLIENTE
            buffer_cli = io.BytesIO()
            with pd.ExcelWriter(buffer_cli, engine='openpyxl') as writer:
                df_cl.to_excel(writer, sheet_name='Historial_Ventas', index=False)
                if not df_cp.empty:
                    df_cp.groupby('Producto')['quantity'].sum().reset_index().to_excel(writer, sheet_name='Productos_Comprados', index=False)
                        
            st.download_button(
                f"📥 Descargar Historial de {cli}",
                data=buffer_cli.getvalue(),
                file_name=f"Historial_{cli[:15]}.xlsx"
            )













