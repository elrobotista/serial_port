import serial
import json
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import threading
import numpy as np

# Puerto Serial
port = serial.Serial('/dev/ttyACM0', 115200, timeout = 1.)

# Creemos los ejes y la figura donde graficaremos.
fig, ax = plt.subplots()

# Este diccionario almacenara los datos del sensor.
signal = {'x': [], 'y': [], 'z': []}

# Estas lineas dibujaran los datos en la figura.
lines = [ax.plot([], [])[0] for _ in signal.iterkeys()]

# Usaremos esta variable para detectar autoescalado de la grafica.
ylim = ()


# La funcion stream sera llamada periodicamente por el timer
# cada numero determinado de milisegundos definido por la variable
# rate.
def stream():
    # Esta es la cadena de caracteres leida por el puerto serial
    # en formato JSON.
    raw_data = port.readline()
    try:
        # El modulo json permite convertir un string en formato JSON a
        # diccionarios de Python. Si el string no viene en el formato adecuado
        # o la informacion se corrompe, el programa nos lo reporta en
        # el bloque de excepcion ValueError;.
        json_data = json.loads(raw_data)
        for k in signal.iterkeys():
            signal[k].append(json_data[k])
    except ValueError:
        print('Could not read data: %s', raw_data)
    # Si el puerto sigue abierto, programamos otra llamada a la funcion para
    # volver a leer el puerto serial.
    if port.is_open:
        threading.Timer(10 / 1000., stream).start()
    else:
        print('Not streaming anymore!')

def animate(i):
    # Las siguientes dos lineas de codigo auto ajustan el eje
    # de las Y en funcion del contenido de la grafica. Me tomo
    # algo de tiempo encontrar estas funciones. Cuidenlo con su
    # alma y compartanlo!
    global ylim
    ax.relim()
    ax.autoscale_view()
    if ax.get_ylim() != ylim:
        # Esta parte del codigo lo que hace es monitorear los valores
        # del limite del eje Y para detectar cuando la grafica ha sido
        # reajustada. Esto para redibujar las etiquetas del eje Y a
        # medida que se reajusta. Si no, las etiquetas permanecen mientras
        # el eje se reajusta. Por lo que los valores no coinciden con lo
        # desplegado en el eje. Los invito a removerlo para que vean a
        # lo que me refiero.
        ylim = ax.get_ylim()
        fig.canvas.draw()
    for name, line in zip(signal.keys(), lines):
    # Si no hay datos nuevos, ni siquiera nos molestamos en intentar
    # graficar.
        if len(signal[name]) > 0:
            _, ly = line.get_data()
            ly = np.append(ly, signal[name])
            _xdata = np.arange(ly.size)
            line.set_data(_xdata, ly)
            # La informacion ha sido graficada. Ya nos podemos deshacer
            # de ella.
            signal[name] = []
        else:
            print('Signal has no data')
    return lines

if __name__ == '__main__':
    ani = animation.FuncAnimation(fig, animate, interval=50, blit=True)
    stream()
    plt.show(block = False)
    while raw_input('Hit Q to exit.\n\r> ').lower() != 'q':
        pass
    port.close()
    
    
