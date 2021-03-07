# Picocad Blender Add On

This add-on brings picocad export to Blender.

![Suzanne in picocad](suzanne.gif)

## Features
* Mesh export.
* Multiple meshes.
* Mesh position, rotation, and scale.
* UV coordinates.
* Texture export.
* Mesh color export.
* Background color export.

## Known Issues
The picocad axes are not the same as Blender's so you will need to rotate your mesh in picocad to make it look the same.

## Installation
Download `blender_picocad.py` from the releases page.

In Blender go to Edit > Preferences, select Add Ons and click Install.
Find the `blender_picocad.py` file.

Make sure you check the box to enable the add-on.

You can find the exporter under File > Export > Picocad.

## Usage
* Create meshes, model, export to picocad.
* If you have a material assigned to a mesh with a Principled BSDF node, the base color will be used for the mesh in picocad. The exporter will map the color to the closest available in picocad.
* If you have a texture node used in a material, the texture will be exported along with your meshes. Note that the texture must be of size 128x128 or smaller.
* UV coordinates will be adjusted to work with picocad and exported along with your meshes.
* If backface culling is enabled in your material, faces will not be double sided in picocad.
* If you set a world color in the scene tab, the color will be saved to the picocad file.
* The filename of your Blender project is used to name the picocad project.

Note: picocad is extremely resource limited, attempting to export meshes with many faces, >100, will likely slow down or crash the program.

### License
The code in this repo is CC0, public domain.