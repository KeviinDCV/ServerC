# ServerC — Monitor de Servidores Windows

Aplicación nativa de Windows para monitorear servidores Windows Server en tiempo real.
Muestra sesiones de usuario conectados, métricas de rendimiento (CPU, RAM, Disco) y alertas de sobrecarga.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Windows](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Características

- **Dashboard multi-servidor**: Vista general de todos los servidores con indicadores de estado
- **Sesiones en tiempo real**: Ver qué usuarios están conectados (RDP/consola), tiempo inactivo, hora de inicio
- **Métricas de rendimiento**: CPU, RAM, Disco, Procesos, Uptime
- **Alertas de sobrecarga**: Umbrales configurables por servidor (amarillo = precaución, rojo = crítico)
- **Credenciales encriptadas**: Las contraseñas se almacenan con cifrado Fernet (AES-128-CBC)
- **Auto-refresh**: Los datos se actualizan automáticamente cada 30 segundos
- **Instalador profesional**: Genera un `.exe` instalable con Inno Setup

---

## Requisitos Previos

### En tu máquina (donde corres la app)
- **Python 3.10+** (para desarrollo) o el `.exe` compilado (para producción)
- **Windows 10/11**

### En los servidores a monitorear
- **WinRM habilitado** (Windows Remote Management)
- **Credenciales de administrador** del servidor

### Habilitar WinRM en los servidores

Ejecuta esto en **PowerShell como Administrador** en cada servidor a monitorear:

```powershell
# Habilitar WinRM
Enable-PSRemoting -Force

# Configurar WinRM para aceptar conexiones remotas
winrm quickconfig -Force

# Permitir autenticación NTLM (necesario para la app)
winrm set winrm/config/service/auth '@{Basic="false";Negotiate="true";Kerberos="true";NTLM="true"}'

# Permitir tráfico sin cifrar en redes internas (HTTP, puerto 5985)
winrm set winrm/config/service '@{AllowUnencrypted="true"}'

# Agregar la IP de tu máquina como host de confianza (en el servidor)
winrm set winrm/config/client '@{TrustedHosts="*"}'
```

> **Nota de seguridad**: En producción, es recomendable usar HTTPS (puerto 5986) en lugar de HTTP.
> Para ello, necesitas instalar un certificado SSL en cada servidor.

### Verificar que WinRM funciona

Desde tu máquina, en PowerShell:

```powershell
Test-WSMan -ComputerName 192.168.14.65 -Authentication Negotiate -Credential (Get-Credential)
```

---

## Instalación (Desarrollo)

```bash
# Clonar el repositorio
git clone <repo-url>
cd ServerC

# Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la app
python main.py
```

---

## Uso

1. **Agregar servidor**: Clic en "＋ Agregar Servidor"
2. **Configurar**:
   - **IP**: Dirección del servidor (ej: `192.168.14.65`)
   - **Usuario**: `Administrador` o `DOMINIO\Administrador`
   - **Contraseña**: Contraseña del administrador
   - **Umbrales**: Número de usuarios para alerta (amarillo) y crítico (rojo)
3. **Probar conexión**: Verifica que la conexión funciona antes de guardar
4. **Monitorear**: El dashboard se actualiza automáticamente cada 30 segundos
5. **Ver detalles**: Clic en cualquier tarjeta de servidor para ver sesiones y métricas detalladas

---

## Compilar Ejecutable (.exe)

```bash
# Activar entorno virtual
venv\Scripts\activate

# Compilar
python build.py
```

El ejecutable estará en `dist/ServerC/ServerC.exe`.

### Crear Instalador

1. Descarga e instala [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Abre el archivo `installer.iss` con Inno Setup
3. Menú **Build > Compile**
4. El instalador se genera en `installer_output/ServerC_Setup_1.0.0.exe`

---

## Estructura del Proyecto

```
ServerC/
├── main.py                    # Punto de entrada
├── requirements.txt           # Dependencias Python
├── build.py                   # Script de compilación
├── build.spec                 # Configuración PyInstaller
├── installer.iss              # Script Inno Setup (instalador)
├── app/
│   ├── models.py              # Modelos de datos
│   ├── config.py              # Gestión de configuración (JSON)
│   ├── server_manager.py      # Lógica de conexión WinRM
│   ├── ui/
│   │   ├── main_window.py     # Ventana principal
│   │   ├── dashboard.py       # Vista dashboard
│   │   ├── server_detail.py   # Vista detalle del servidor
│   │   ├── add_server.py      # Diálogo agregar/editar servidor
│   │   └── styles.py          # Colores y fuentes
│   └── utils/
│       └── crypto.py          # Encriptación de contraseñas
└── assets/
    └── icon.ico               # Ícono de la aplicación (opcional)
```

---

## Datos Almacenados

La configuración se guarda en:
```
%APPDATA%\ServerC\servers.json    — Lista de servidores (contraseñas encriptadas)
%APPDATA%\ServerC\.key            — Clave de cifrado
```

---

## Tecnologías

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.10+ |
| UI | CustomTkinter (nativo Windows) |
| Conexión remota | WinRM + NTLM (pywinrm) |
| Cifrado | Fernet / PBKDF2 (cryptography) |
| Compilación | PyInstaller |
| Instalador | Inno Setup |

---

## Solución de Problemas

| Problema | Solución |
|---|---|
| "Error de conexión: WinRM..." | Verificar que WinRM está habilitado en el servidor |
| "Access denied" | Verificar credenciales de administrador |
| "Connection refused" | Verificar firewall (puerto 5985/5986) |
| La app no detecta sesiones | El servidor debe tener el rol de Remote Desktop Services |
| Timeout al conectar | Verificar conectividad de red (`ping <ip>`) |
