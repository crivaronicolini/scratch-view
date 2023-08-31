from ij import IJ
import os
#@ String carpeta
#@ boolean (label="Derecha a izquierda") der_izq


files = [i for i in os.listdir(carpeta) if i.endswith('bmp') or i.endswith('jpg')]
ext = files[0][-3:]
x=len(files)
print(ext)
y = 1
overlap = 10
salida = carpeta + ".jpg"
if der_izq:
    order = "Right & Down"
else:
    order = "Left & Down"
print(salida)

IJ.run("Grid/Collection stitching",
       "type=[Grid: row-by-row] order=["+ order + "                ] grid_size_x="+str(x)+" grid_size_y="+str(y)+" tile_overlap="+str(overlap)+" first_file_index_i=1 directory=["+str(carpeta)+" ] file_names={i}."+str(ext)+" output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.10 xmax/avg_displacement_threshold=0.10 absolute_displacement_threshold=0.10 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]")
imp = IJ.getImage()
IJ.saveAs(imp, "Jpeg", salida)
       # "type=[Grid: row-by-row] order=[Right & Down                ] grid_size_x="+str(x)+" grid_size_y="+str(y)+" tile_overlap="+str(overlap)+" first_file_index_i=1 directory=["+str(carpeta)+" ] file_names={i}."+str(ext)+" output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 xmax/avg_displacement_threshold=0.50 absolute_displacement_threshold=0.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]")
