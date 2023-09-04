<p align="center">
  <img width="128" src="https://user-images.githubusercontent.com/33268188/233685530-d7a40af1-30d1-41fb-8b86-35475dbff597.svg">
</p>

# Scratch View
Interfaz gráfica para analizar huellas de ensayo de rayado y los datos recopilados por Scratch Tester.

![image](https://user-images.githubusercontent.com/33268188/233167113-d06070fa-9acb-445a-b556-56b4e9037435.png)

Los ensayos de rayado dinámicos evalúan la adhesion que tiene un recubrimiento al sustrato aplicando una carga controlada y creciente.
Este programa permite sincronizar una foto panoramica de la huella dejada por el ensayo con la carga medida por el equipo.
Con este análisis se puede identificar cada ruptura por la carga que la generó, y así estudiar la adhesion del recubrimiento.

## Uso
1. Arrastrar la imagen de la raya y el `.csv` al programa para abrir el ensayo.
2. Elegir el origen de la raya con el boton `definir origen` y haciendo click derecho en principio de la raya.
3. En la parte inferior de la ventana se muestra la posición del mouse y la fuerza medida en ese lugar.
4. Con la función `marcar rayas` se pueden marcar las roturas de interés.
5. En el menú `Archivo` se puede guardar la imagen con las marcas amarillas y por separado un archivo con la fuerza realizada en esas marcas.

## Instalación
En el apartado de [releases](https://github.com/crivaronicolini/scratch-view/releases) están las carpetas con el código empaquetado.
1. Descargar el archivo correspondiente al sistema operativo (ej. Windows)
2. Descomprimir la carpeta
3. Adentro está el archivo `scratch-view.exe`, se puede usar directamente o crear un acceso directo en el escritorio.

## Empaquetado
El programa se empaqueta con `pyinstaller` en la plataforma de destino.
Para hacer esto Windows, con python 3.10 instalado (o python 3.8.6 para Windows 7), descargar el repositorio como un `.zip` (en el boton verde arriba de esta pagina).
Abrir la carpeta con los archivos en una terminal de Windows y correr lo siguiente:
```{shell}
  pip install -r requirements.txt
  pyinstaller scratch-view.spec
```
Se creará una carpeta `dist/` que es la distribuible, igual a la que se encuentra en [releases](https://github.com/crivaronicolini/scratch-view/releases).
Alternativamente se puede usar directo el programa sin empaquetar, corriendo `python scratch-view.py` en una terminal.
