import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import os
import time # Necesario para la limpieza (simulación)

# --- Configuración de la Página ---
st.set_page_config(
    page_title="AliadoDoc",
    page_icon="🧠",
    layout="wide"
)

# --- SISTEMA DE CONDUCTA (TU GEM) ---
# 🚨 PEGA TU PROMPT COMPLETO DE CONDUCTA AQUÍ 🚨
SISTEMA_DE_CONDUCTA = os.environ.get("GEM_PROMPT", 'aaa')

# --- Barra Lateral para Configuración ---
with st.sidebar:
    
    st.title("AliadoDoc")
    st.header("⚙️ Configuración")
    
    # 1. Cargar API Key desde Colab Secrets
    # Usar '' como fallback para que el entorno de Canvas pueda inyectar la clave
    api_key = os.environ.get("GEMINI_API_KEY", '')     
    
    
    model_option = st.selectbox(
        "Selecciona el Modelo",
        ("gemini-2.5-pro", "gemini-2.5-flash")
    )
 
# --- Funciones Auxiliares para Archivos ---

def upload_file_to_gemini(api_key, uploaded_file):
    """Sube el archivo a la API de Archivos de Gemini."""
    if not api_key:
        st.error("Error: La clave API no está configurada. No se puede subir el archivo.")
        return None
    
    try:
        genai.configure(api_key=api_key)
        
        # Volver al inicio del buffer y leer los bytes
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()

        # Crear un objeto io.BytesIO para pasarlo a la función
        file_data = io.BytesIO(file_bytes)
        
        # Subir el archivo
        with st.spinner(f"Subiendo '{uploaded_file.name}' a Gemini para análisis..."):
             file_obj = genai.client.files.upload(
                file=file_data, 
                display_name=uploaded_file.name,
                mime_type=uploaded_file.type
            )
        st.toast("Archivo binario subido con éxito a la API de Archivos.")
        return file_obj
        
    except Exception as e:
        st.error(f"Error al subir archivo a Gemini: {e}")
        return None

def delete_file_from_gemini(api_key, file_obj):
    """Elimina el archivo de la API de Archivos de Gemini (limpieza)."""
    if not api_key: return # No intentar eliminar si no hay clave
    if not file_obj: return
    try:
        genai.configure(api_key=api_key)
        genai.client.files.delete(name=file_obj.name)
        st.toast(f"Archivo de Gemini '{file_obj.display_name}' eliminado.")
    except Exception as e:
        # Esto puede fallar si el archivo ya fue eliminado o expiró
        print(f"Advertencia: No se pudo eliminar el archivo de Gemini: {e}")
        pass # Ignorar errores de limpieza para no detener la aplicación

def get_gemini_response(api_key, model_name, user_prompt, system_instruction, content_files=None):
    """Función para interactuar con la API de Gemini."""
    
    try:
        if api_key:
             genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        generation_parts = [user_prompt]
        if content_files:
            generation_parts.extend(content_files)

        with st.spinner("Generando respuesta..."):
             response = model.generate_content(generation_parts, stream=True)
        return response
    except Exception as e:
        if "API key not valid" in str(e):
             return "⚠️ Error de Clave API: La clave proporcionada (GEMINI_API_KEY) no es válida. Por favor, verifica tu configuración."
        return f"❌ Error: {str(e)}"

def process_uploaded_file(api_key, uploaded_file):
    """Procesa el archivo subido: lo convierte a PIL.Image, texto (str) o lo sube a Gemini (File object)."""
    if uploaded_file is None: return None
    mime_type = uploaded_file.type
    
    # 1. Archivos de imagen (PIL.Image)
    if mime_type.startswith('image'):
        try:
            uploaded_file.seek(0)
            return Image.open(io.BytesIO(uploaded_file.read()))
        except Exception as e: 
            st.error(f"Error al procesar la imagen: {e}")
            return None
            
    # Lista de extensiones que Gemini requiere subir a su API de Archivos (Binarios)
    binary_extensions = ('.doc', '.docx', '.pdf', '.xls', '.xlsx')
    
    # 2. Archivos Binarios (PDF, Word, Excel)
    if uploaded_file.name.lower().endswith(binary_extensions) or mime_type in ['application/pdf', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        # Subir el archivo binario a la API de Archivos de Gemini
        return upload_file_to_gemini(api_key, uploaded_file)
            
    # 3. Archivos de Texto (String) - (txt, py, md, csv, json)
    elif mime_type.startswith('text') or mime_type == 'application/json' or uploaded_file.name.endswith(('.py', '.md', '.csv', '.txt')):
        try:
            uploaded_file.seek(0)
            return uploaded_file.read().decode("utf-8")
        except Exception as e: 
            st.error(f"Error al leer el archivo de texto: {e}. Asegúrese de que es texto plano.")
            return None
            
    st.error(f"Tipo de archivo no soportado o formato inválido: {mime_type}")
    return None

# --- Interfaz Principal ---

# Inicializar sesión para gestión de archivos
if 'uploaded_file_data' not in st.session_state:
    st.session_state.uploaded_file_data = None # Contenido procesado (Image, str o Gemini File object)
if 'uploaded_file_name' not in st.session_state:
    st.session_state.uploaded_file_name = None # Nombre del archivo
if 'gemini_file_obj' not in st.session_state:
    st.session_state.gemini_file_obj = None # Objeto File de Gemini para limpieza
if 'prompt_from_button' not in st.session_state:
    st.session_state.prompt_from_button = None

# --- Obtener contenido de la sesión para usar y mostrar ---
processed_content = st.session_state.uploaded_file_data
file_name_to_display = st.session_state.uploaded_file_name
gemini_file_obj = st.session_state.gemini_file_obj

# Mostrar la previsualización del contenido guardado en la sesión
if processed_content:
    st.subheader(f"Archivo en Sesión: {file_name_to_display}")
    
    # Mostrar preview según el tipo de contenido
    if isinstance(processed_content, Image.Image):
        st.image(processed_content, caption="Imagen cargada", width=300)
    elif gemini_file_obj:
        st.markdown(f"**Archivo Binario:** Subido con éxito a Gemini (ID: `{gemini_file_obj.name.split('/')[-1]}`).")
        st.info("Nota: Los archivos binarios (PDF, DOCX, XLSX) no se previsualizan directamente aquí, pero están listos para el análisis de Gemini.")
    else:
        # Contenido de texto
        st.text_area("Previsualización:", value=str(processed_content)[:1000], height=100, help="Mostrando los primeros 1000 caracteres.")
    
    # Botón para limpiar la subida de sesión
    if st.button("🗑️ Eliminar archivo de la sesión y de Gemini"):
        # 1. Eliminar de la API de Gemini si existe
        if gemini_file_obj:
            delete_file_from_gemini(api_key, gemini_file_obj)
        
        # 2. Limpiar el estado de sesión
        st.session_state.uploaded_file_data = None
        st.session_state.uploaded_file_name = None
        st.session_state.gemini_file_obj = None
        st.toast("Archivos eliminados. La sesión está limpia.")
        st.rerun() 

# =================================================================
# BLOQUE DE CARGA DE ARCHIVOS
# =================================================================
with st.expander("📂 Cargar Archivos (Imágenes, Texto, PDF, Word, Excel)", expanded=True):
    current_uploaded_file = st.file_uploader(
        "Arrastra tu archivo aquí (Pulsa 'Guardar' para enviarlo a la sesión de chat)", 
        type=["jpg", "png", "txt", "csv", "py", "md", "doc", "docx", "pdf", "xlsx", "xls"], 
        key="file_uploader_widget"
    )
    
    if current_uploaded_file is not None:
        if st.button("💾 Guardar Archivo en Sesión", key="save_file_btn"):
            
            # Limpiar cualquier archivo binario anterior antes de procesar el nuevo
            if st.session_state.gemini_file_obj:
                 delete_file_from_gemini(api_key, st.session_state.gemini_file_obj)
                 st.session_state.gemini_file_obj = None # Asegurar que se limpia

            st.session_state.uploaded_file_name = current_uploaded_file.name
            
            # --- PROCESAR EL ARCHIVO ---
            # Ahora pasamos la api_key a process_uploaded_file para la subida binaria
            processed_data = process_uploaded_file(api_key, current_uploaded_file)
            st.session_state.uploaded_file_data = processed_data
            
            # Si el resultado es un objeto File de Gemini, guárdalo para la limpieza
            if processed_data and hasattr(processed_data, 'name'):
                st.session_state.gemini_file_obj = processed_data
                
            # --- FIN PROCESAMIENTO ---
            
            if st.session_state.uploaded_file_data is not None:
                st.toast(f"Archivo '{current_uploaded_file.name}' cargado a la sesión. ¡Listo para chatear!", icon='💾')
            else:
                st.toast("Error al cargar el archivo. Por favor, revisa el formato.", icon='❌')
                
            st.rerun()
            

# =================================================================
# FIN DEL BLOQUE DE CARGA DE ARCHIVOS
# =================================================================

# --- BOTONES DE ACCIONES RÁPIDAS ---
st.markdown("---")
st.subheader("🚀 Acciones Rápidas")
col1, col2 = st.columns(2)

# Botón 1: Asesoría Rápida (Iniciar Proyecto)
if col1.button("🧠 Asesoría Rápida (Iniciar Proyecto)", use_container_width=True):
    st.session_state.prompt_from_button = "Necesito una guía rápida paso a paso para iniciar un nuevo proyecto. Asume que no tengo experiencia en gestión de proyectos."
    st.rerun() 

# Botón 2: Descargar Formatos Esenciales
format_content = """
# Plantillas y Formatos de Proyecto

Aquí tienes un esqueleto de documento:

Tipo de documento (instructivo, guía o procedimiento)
Título del documento
Objetivo
Alcance
Contexto o proceso asociado
Actividades o pasos
Responsables
Registros o evidencias
Indicaciones de formato institucional

---
*Nota: En una aplicación real, estos serían enlaces directos de descarga.*
"""
col2.download_button(
    label="⬇️ Descargar Formatos Esenciales",
    data=format_content,
    file_name="Formatos_Esenciales_AliadoDoc.md",
    mime="text/markdown",
    use_container_width=True
)
st.markdown("---")

# Inicializar historial de chat en session_state si no existe
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "¡Hola! Soy AliadoDoc. **Ahora puedo analizar PDF, Word y Excel** además de imágenes y texto plano. Sube un archivo o usa los botones de 'Acciones Rápidas' para comenzar."
    }]

# Mostrar mensajes anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --- Lógica de Chat Unificada ---
prompt_from_button = st.session_state.pop('prompt_from_button', None)
prompt_from_chat = st.chat_input("Escribe tu mensaje...")
user_prompt = prompt_from_button or prompt_from_chat

if user_prompt:
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        attachment_msg = ""
        if file_name_to_display:
            attachment_msg = f" (Archivo Adjunto: **{file_name_to_display}**)"
        st.markdown(user_prompt + attachment_msg)

    with st.chat_message("assistant"):
        msg_placeholder = st.empty()
        full_response = ""
        
        # OBTENER LISTA DE CONTENIDO: Si es un objeto File de Gemini, solo enviamos ese objeto.
        content_list = []
        if processed_content: 
            content_list.append(processed_content) 
        
        # Llamada a la API
        response_stream = get_gemini_response(api_key, model_option, user_prompt, SISTEMA_DE_CONDUCTA, content_list)
        
        if isinstance(response_stream, str):
            msg_placeholder.markdown(response_stream)
            full_response = response_stream
            if "Error de Clave API" in full_response:
                st.session_state.messages.pop() 
                st.session_state.messages.pop() 
                st.rerun()
        else:
            try:
                for chunk in response_stream:
                    if chunk.text:
                        full_response += chunk.text
                        msg_placeholder.markdown(full_response + "▌")
                msg_placeholder.markdown(full_response)
            except Exception as e:
                st.error(f"Error al procesar la respuesta del modelo: {e}")
                
        # --- LIMPIEZA POST-RESPUESTA ---
        # Si se usó un archivo binario, se debe eliminar después de obtener la respuesta.
        if gemini_file_obj:
            delete_file_from_gemini(api_key, gemini_file_obj)
            # Limpiar el estado de sesión para evitar que se use en la siguiente pregunta
            st.session_state.uploaded_file_data = None
            st.session_state.uploaded_file_name = None
            st.session_state.gemini_file_obj = None
            st.rerun()
            
        st.session_state.messages.append({"role": "assistant", "content": full_response})
