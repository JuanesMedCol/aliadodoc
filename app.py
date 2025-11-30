import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import os
import time
from pathlib import Path
import zipfile
import re

# --- Configuración de la Página ---
st.set_page_config(
    page_title="AliadoDoc",
    page_icon="🧠",
    layout="wide"
)

# --- SISTEMA DE CONDUCTA (TU GEM) ---
# 🚨 PEGA TU PROMPT COMPLETO DE CONDUCTA AQUÍ 🚨
SISTEMA_DE_CONDUCTA = os.environ.get("GEM_PROMPT", 'Actúa como un asistente experto en creación de documentos institucionales.')


# === Helpers para descargas de documentos del repositorio ===

REPO_ROOT = Path(__file__).parent  # Carpeta donde está este archivo .py

@st.cache_data
def cargar_bytes_archivo(ruta_relativa: str) -> bytes:
    """
    Lee un archivo binario del repositorio y devuelve sus bytes.
    ruta_relativa es relativa al archivo actual (ej: 'docs/Plantilla_Guia.docx').
    """
    file_path = REPO_ROOT / ruta_relativa
    with open(file_path, "rb") as f:
        return f.read()

def crear_zip_documentos(archivos: dict) -> io.BytesIO:
    """
    Crea un ZIP en memoria con varios archivos.
    archivos: dict {nombre_en_zip: bytes}
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre_zip, contenido in archivos.items():
            zf.writestr(nombre_zip, contenido)
    buffer.seek(0)
    return buffer


# --- Funciones Auxiliares para Archivos (Mantenidas) ---

def upload_file_to_gemini(api_key, uploaded_file):
    """
    Sube el archivo a la API de Archivos de Gemini usando google-generativeai.
    """
    if not api_key:
        st.error("Error: La clave API no está configurada. No se puede subir el archivo binario.")
        return None

    try:
        genai.configure(api_key=api_key)

        # Guardamos el archivo de Streamlit en un path temporal
        tmp_dir = "/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, uploaded_file.name)

        uploaded_file.seek(0)
        with open(tmp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with st.spinner(f"Subiendo '{uploaded_file.name}' a Gemini para análisis..."):
            # SDK viejo: usa upload_file(path=...)
            file_obj = genai.upload_file(
                path=tmp_path,
                display_name=uploaded_file.name,
            )

        st.toast("Archivo binario subido con éxito a la API de Archivos.")
        return file_obj

    except AttributeError as e:
        # Aquí llegarías si tu versión es TAN vieja que ni siquiera tiene upload_file
        error_msg = (
            "❌ ERROR DE COMPATIBILIDAD DE LIBRERÍA: La funcionalidad de subida de "
            "archivos binarios (PDF, DOCX, XLSX) **no está soportada** en la versión "
            "de la biblioteca `google-generativeai` instalada. "
            "Actualiza el paquete `google-generativeai` a una versión reciente."
        )
        st.error(error_msg)
        print(f"DEBUG: Error completo de subida a Gemini (Incompatibilidad de Librería): {e}")
        return None

    except Exception as e:
        error_msg = f"❌ Error general al subir archivo binario: {e}. "
        if "API key not valid" in str(e) or "authentication" in str(e):
            error_msg += (
                "Por favor, **REVISA TU CLAVE API (GEMINI_API_KEY)**, la subida falló por autenticación."
            )
        elif "Unsupported" in str(e) or "format" in str(e):
            error_msg += "El formato del archivo podría no estar soportado por la API de Archivos."
        st.error(error_msg)
        print(f"DEBUG: Error completo de subida a Gemini (General): {e}")
        return None


def delete_file_from_gemini(api_key, file_obj):
    """Elimina el archivo de la API de Archivos de Gemini (limpieza)."""
    if not api_key or not file_obj:
        return
    try:
        genai.configure(api_key=api_key)
        # SDK viejo: delete_file(name=...)
        genai.delete_file(name=file_obj.name)
        st.toast(f"Archivo de Gemini '{getattr(file_obj, 'display_name', file_obj.name)}' eliminado.")
    except AttributeError:
        # Si tampoco existe delete_file, ignoramos silenciosamente
        pass
    except Exception as e:
        print(f"Advertencia: No se pudo eliminar el archivo de Gemini: {e}")
        pass

def get_gemini_response(api_key, model_name, user_prompt, system_instruction, content_files=None):
    """Función para interactuar con la API de Gemini con manejo de cuota y temporizador."""
    try:
        if api_key:
            genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        generation_parts = [user_prompt]
        if content_files:
            # Filtramos el contenido. Si el proceso de subida falló (devuelve None), 
            # no queremos incluirlo en generation_parts.
            valid_content = [c for c in content_files if c is not None]
            generation_parts.extend(valid_content)

        with st.spinner("Generando respuesta..."):
            response = model.generate_content(generation_parts, stream=True)
        return response

    except Exception as e:
        msg = str(e)

        # --- Manejo de cuota / 429 ---
        if ("429" in msg or "quota" in msg.lower() or "exceeded your current quota" in msg):
            # Intentar extraer el tiempo de reintento desde el texto del error.
            retry_seconds = None

            # Caso 1: "Please retry in 55.523970349s"
            m = re.search(r"retry in ([0-9\.]+)s", msg)
            if m:
                try:
                    retry_seconds = float(m.group(1))
                except ValueError:
                    retry_seconds = None

            # Caso 2: "retry_delay { seconds: 55 }"
            if retry_seconds is None:
                m2 = re.search(r"retry_delay\s*\{\s*seconds:\s*([0-9]+)", msg)
                if m2:
                    try:
                        retry_seconds = float(m2.group(1))
                    except ValueError:
                        retry_seconds = None

            base_msg = (
                "⚠️ **Has alcanzado el límite de uso de la API para este modelo.**\n\n"
                f"Modelo actual: `{model_name}`.\n\n"
                "Esto suele ocurrir con el plan gratuito cuando se hacen muchas solicitudes "
                "en poco tiempo o se supera el número diario permitido.\n"
            )

            if retry_seconds is not None:
                minutos = int(retry_seconds // 60)
                segundos = int(round(retry_seconds % 60))
                if minutos > 0:
                    tiempo_str = f"**{minutos} min {segundos} s**"
                else:
                    tiempo_str = f"**{segundos} s**"

                base_msg += (
                    f"\n⏱️ Podrás reintentar aproximadamente en {tiempo_str}.\n"
                )

            base_msg += (
                "\n💡 Recomendaciones:\n"
                "- Cambia al modelo `gemini-2.5-flash` en la barra lateral (consume menos cuota).\n"
                "- Si necesitas seguir usando este modelo, revisa tu plan y facturación en la consola de Google.\n"
            )
            return base_msg

        # --- Manejo de clave API inválida ---
        if "API key not valid" in msg:
            return (
                "⚠️ **Error de Clave API**: La clave proporcionada (GEMINI_API_KEY) "
                "no es válida o no tiene permisos. Revisa tu configuración."
            )

        # --- Otros errores genéricos ---
        return f"❌ Error: {msg}"

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
    if uploaded_file.name.lower().endswith(binary_extensions) or mime_type in [
        'application/pdf', 
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', # XLSX
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', # DOCX
        'application/msword', # DOC
        'application/vnd.ms-excel' # XLS
        ]:
        
        # Subir el archivo binario a la API de Archivos de Gemini
        return upload_file_to_gemini(api_key, uploaded_file)
            
    # 3. Archivos de Texto (String) - (txt, py, md, csv, json, etc.)
    elif mime_type.startswith('text') or uploaded_file.name.endswith(('.py', '.md', '.csv', '.txt', '.json')):
        try:
            uploaded_file.seek(0)
            return uploaded_file.read().decode("utf-8")
        except Exception as e: 
            st.error(f"Error al leer el archivo de texto: {e}. Asegúrese de que es texto plano.")
            return None
            
    st.error(f"Tipo de archivo no soportado o formato inválido: {mime_type}")
    return None


# Inicializar sesión para gestión de archivos (Necesario antes de usar en el sidebar)
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


# --- Barra Lateral para Configuración, Acciones Rápidas y Carga de Archivos ---
with st.sidebar:
    
    st.title("AliadoDoc")
    st.header("⚙️ Configuración")
    
    # 1. Cargar API Key desde Colab Secrets
    api_key = os.environ.get("GEMINI_API_KEY", '')     
    
    
    model_option = st.selectbox(
        "Selecciona el Modelo",
        ("gemini-2.5-flash", "gemini-2.5-pro")
    )
    
    # --- BOTONES DE ACCIONES RÁPIDAS ---
    st.markdown("---")
    st.subheader("Acciones")

    # Botón 1: Asesoría Rápida (Iniciar Proyecto)
    if st.button("Asesoría Rápida", use_container_width=True, key="quick_start_btn"):
        st.session_state.prompt_from_button = """
        Cordial Saludo, deseo que me apoyes con los siguientes temas:
        - Qué información falta según los campos obligatorios y cual de la informacion disponible podria ayudarme a completarla.
        - Cómo completarla, con sugerencias, usuando el documento suministrado y apoyar con el orden del documento.
        - hay algun estandar documental que podria tener en cuenta para mejorar el documento?
        - Si no tengo nada o hay algo faltante, dame un ejemplo básico para orientarme en el tema faltante.
        """
        st.rerun() 

    # if st.button("Generar Formatos", use_container_width=True, key="fast_format_btn"):
    #     st.session_state.prompt_from_button = "Me podrias dar un formato en blanco de cada tipo de documento (Instructivo, Guia y Procedimiento) en MD?."
    #     st.rerun() 

    # =================================================================
    # BLOQUE DE DESCARGA DE PLANTILLAS
    # =================================================================
    
    with st.expander("📑 Descarga de Plantillas"):
        try:
            # Cargar bytes de las tres plantillas desde el repositorio
            guia_bytes = cargar_bytes_archivo("docs/Plantilla_Guia.docx")
            instructivo_bytes = cargar_bytes_archivo("docs/Plantilla_Instructivo.docx")
            procedimiento_bytes = cargar_bytes_archivo("docs/Plantilla_Procedimiento.docx")
    
            # Botón para la Plantilla Guía
            st.download_button(
                label="Guía",
                data=guia_bytes,
                file_name="Plantilla_Guia.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_guia"
            )
    
            # Botón para la Plantilla Instructivo
            st.download_button(
                label="Instructivo",
                data=instructivo_bytes,
                file_name="Plantilla_Instructivo.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_instructivo"
            )
    
            # Botón para la Plantilla Procedimiento
            st.download_button(
                label="Procedimiento",
                data=procedimiento_bytes,
                file_name="Plantilla_Procedimiento.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_procedimiento"
            )
    
            # Botón para descargar todas en un ZIP
            archivos_zip = {
                "Plantilla_Guia.docx": guia_bytes,
                "Plantilla_Instructivo.docx": instructivo_bytes,
                "Plantilla_Procedimiento.docx": procedimiento_bytes,
            }
            zip_buffer = crear_zip_documentos(archivos_zip)
    
            st.download_button(
                label="🗂️ Todas",
                data=zip_buffer,
                file_name="Plantillas_AliadoDoc.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_zip_all"
            )
    
        except FileNotFoundError:
            st.error(
                "❌ No se encontraron las plantillas en el repositorio.\n\n"
                "Asegúrate que existan en:\n"
                "- docs/Plantilla_Guia.docx\n"
                "- docs/Plantilla_Instructivo.docx\n"
                "- docs/Plantilla_Procedimiento.docx"
            )


    # =================================================================
    # BLOQUE DE CARGA Y PREVIEW DE ARCHIVOS (MOVIMIENTO AL SIDEBAR)
    # =================================================================

    # 1. PREVISUALIZACIÓN Y ELIMINACIÓN
    # Mostrar la previsualización del contenido guardado en la sesión
    if processed_content:
        st.subheader(f"Archivo en Sesión: {file_name_to_display}")
        
        # Mostrar preview según el tipo de contenido
        if isinstance(processed_content, Image.Image):
            st.image(processed_content, caption="Imagen cargada", use_column_width=True)
        elif gemini_file_obj:
            st.markdown(f"**Archivo Binario:** Subido con éxito a Gemini (ID: `{gemini_file_obj.name.split('/')[-1]}`).")
            st.info("Nota: Los archivos binarios (PDF, DOCX, XLSX) no se previsualizan directamente aquí.")
        elif processed_content is not None:
            # Contenido de texto
            # Usamos un key para evitar posibles conflictos de rerender en el sidebar
            st.text_area("Previsualización:", value=str(processed_content)[:500], height=100, help="Mostrando los primeros 500 caracteres.", key="sidebar_preview")
        
        # Botón para limpiar la subida de sesión
        if st.button("🗑️ Eliminar archivo de la sesión y de Gemini", use_container_width=True, key="delete_sidebar_btn"):
            # 1. Eliminar de la API de Gemini si existe
            if gemini_file_obj:
                delete_file_from_gemini(api_key, gemini_file_obj)
            
            # 2. Limpiar el estado de sesión
            st.session_state.uploaded_file_data = None
            st.session_state.uploaded_file_name = None
            st.session_state.gemini_file_obj = None
            st.toast("Archivos eliminados. La sesión está limpia.")
            st.rerun() 
            
        st.markdown("---") 

    # 2. UPLOADER 
    with st.expander("📂 Cargar Archivos"):
        current_uploaded_file = st.file_uploader(
            "Arrastra tu archivo aquí (Pulsa 'Guardar' para enviarlo a la sesión de chat)", 
            type=["jpg", "png", "txt", "csv", "py", "json", "md", "pdf", "doc", "docx", "xls", "xlsx"], 
            key="file_uploader_widget"
        )
        
        if current_uploaded_file is not None:
            if st.button("💾 Guardar Archivo en Sesión", key="save_file_btn", use_container_width=True):
                
                # Limpiar cualquier archivo binario anterior antes de procesar el nuevo
                if st.session_state.gemini_file_obj:
                    delete_file_from_gemini(api_key, st.session_state.gemini_file_obj)
                    st.session_state.gemini_file_obj = None 

                st.session_state.uploaded_file_name = current_uploaded_file.name
                
                # --- PROCESAR EL ARCHIVO ---
                processed_data = process_uploaded_file(api_key, current_uploaded_file)
                st.session_state.uploaded_file_data = processed_data
                
                # Si el resultado es un objeto File de Gemini, guárdalo para la limpieza
                if processed_data and hasattr(processed_data, 'name'):
                    st.session_state.gemini_file_obj = processed_data
                # Si la subida falló (devuelve None), asegurarnos de que no hay objeto de archivo en sesión
                elif processed_data is None:
                    st.session_state.uploaded_file_name = None
                    
                # --- FIN PROCESAMIENTO ---
                
                if st.session_state.uploaded_file_data is not None:
                    st.toast(f"Archivo '{current_uploaded_file.name}' cargado a la sesión. ¡Listo para chatear!", icon='💾')
                else:
                    st.toast("El archivo no pudo ser cargado. Revisa los errores arriba.", icon='❌')
                    
                st.rerun()
    # =================================================================
    # FIN DEL BLOQUE DE CARGA Y PREVIEW DE ARCHIVOS
    # =================================================================

# --- Interfaz Principal (Resto del código) ---

# El bloque de previsualización y el bloque de carga de archivos han sido eliminados de aquí.


# Inicializar historial de chat en session_state si no existe
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": """
        ## ¡Hola! Soy **AliadoDoc**.

        Mi función es apoyarte con tus necesidades documentales ya sea con:

            - Instructivos
            - Guias
            - Procedimientos

        De igual forma, puedo asistirte en la creación, revisión y mejora de documentos institucionales.

        Y como reecomendacion previa te sugiero una estructura básica para tus documentos:
            
            - Tipo de documento (instructivo, guía o procedimiento)
            - Título del documento
            - Objetivo
            - Alcance
            - Contexto o proceso asociado
            - Actividades o pasos
            - Responsables
            - Registros o evidencias
            - Indicaciones de formato institucional

        Antes de comenzar, por favor asegúrate de haber cargado cualquier archivo que desees que revise.

        ¿En qué puedo ayudarte hoy?
        
        """
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
        # Solo muestra el adjunto si el contenido no es None (es decir, la subida tuvo éxito o es una imagen/texto)
        if file_name_to_display and processed_content is not None: 
            attachment_msg = f" (Archivo Adjunto: **{file_name_to_display}**)"
        st.markdown(user_prompt + attachment_msg)

    with st.chat_message("assistant"):
        msg_placeholder = st.empty()
        full_response = ""
        
        # OBTENER LISTA DE CONTENIDO: Se adjunta el contenido procesado si existe.
        content_list = []
        if processed_content: 
            content_list.append(processed_content) 
        
        # Llamada a la API
        response_stream = get_gemini_response(api_key, model_option, user_prompt, SISTEMA_DE_CONDUCTA, content_list)
        
        def extraer_texto_de_chunk(chunk) -> str:
            """
            Extrae texto de un chunk de respuesta de Gemini de forma segura,
            sin usar chunk.text para evitar errores cuando no hay Parts válidos.
            """
            try:
                candidates = getattr(chunk, "candidates", None)
                if not candidates:
                    return ""
                
                cand = candidates[0]
                content = getattr(cand, "content", None)
                if not content:
                    return ""
                
                parts = getattr(content, "parts", None)
                if not parts:
                    return ""
                
                textos = []
                for part in parts:
                    t = getattr(part, "text", None)
                    if t:
                        textos.append(t)
                
                return "".join(textos)
            except Exception:
                # Si la estructura no es la esperada, devolvemos vacío y ya
                return ""
        

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
                    # Extraer texto de forma segura, sin usar chunk.text
                    chunk_text = extraer_texto_de_chunk(chunk)
                    if chunk_text:
                        full_response += chunk_text
                        msg_placeholder.markdown(full_response + "▌")

                if full_response.strip():
                    # Sí hubo texto en la respuesta
                    msg_placeholder.markdown(full_response)
                else:
                    # No hubo texto en ningún chunk: probablemente bloqueo de seguridad o respuesta vacía
                    msg_placeholder.markdown(
                        "⚠️ El modelo no pudo devolver texto. "
                        "Es posible que la respuesta haya sido bloqueada por las políticas "
                        "de seguridad de Gemini o que la petición no haya generado contenido."
                    )
            except Exception as e:
                st.error(f"Error al procesar la respuesta del modelo: {e}")


        # --- LIMPIEZA POST-RESPUESTA ---
        # Si se usó un archivo binario (objeto File de Gemini), se elimina después de obtener la respuesta.
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response
        })