bl_info = {
    'name': 'Blender Picocad',
    'description': 'Export to picocad.',
    'blender': (2, 80, 0),
    'category': 'Import-Export',
    'location': 'File > Export > Picocad',
    'author': 'davabase',
}


import bpy
import os

from bpy_extras.io_utils import ExportHelper
from math import sqrt
from mathutils import Color, Vector, Euler


class PicocadExporter(bpy.types.Operator, ExportHelper):
    """Picocad Exporter"""
    bl_idname = 'import_export.picocad'
    bl_label = 'Export to Picocad'
    bl_options = {'REGISTER'}

    # From ExporterHelper.
    filename_ext = '.txt'
    def execute(self, context):
        # Get the filename.
        filename = os.path.splitext(bpy.path.basename(context.blend_data.filepath))[0]
        if not filename:
            filename = 'untitled'

        # Get the scene background color.
        back_color = color_to_picocad_index(context.scene.world.color)

        # We use the image found in the material of the first mesh for the texture.
        image = None
        width = None
        height = None

        # Print the header.
        # picocad, file name, zoom level, background color, alpha color.
        output = 'picocad;{};16;{};0\n'.format(filename, back_color)
        output += '{\n'

        # We loop through objects instead of meshes since mesh data sticks around even after an object is deleted.
        for name, object in bpy.data.objects.items():
            if object.type != 'MESH':
                continue
            data = bpy.data.meshes[name]
            location = object.location

            double_sided = True
            mesh_color = '6'

            # Get information from the first assigned material.
            if len(object.material_slots) > 0:
                material = object.active_material

                # Check if backface culling is enabled.
                double_sided = not material.use_backface_culling

                # Get the first image texture, no need to make this more complicated.
                if material.use_nodes:
                    if not image:
                        for node in material.node_tree.nodes:
                            if node.type == 'TEX_IMAGE':
                                # Only use the texture if it is actually linked.
                                if len(node.outputs['Color'].links) > 0:
                                    image = node.image
                                    break

                    # If no image is provided to the material, attempt to get the base color of a principled BSDF shader.
                    if not image:
                        for node in material.node_tree.nodes:
                            if node.type == 'BSDF_PRINCIPLED':
                                # Only use this shader if it is actually linked.
                                if len(node.outputs['BSDF'].links) > 0:
                                    base_color = node.inputs[0].default_value
                                    mesh_color = color_to_picocad_index(Color((base_color[0], base_color[1], base_color[2])))
                                    break
                else:
                    self.report({'WARNING'}, 'Material must use nodes to find image texture or mesh color. Ignoring texture export and mesh color.')

            # Get the texture size.
            # Notice, this expects the texture assigned to the material to be the same one used in the UV map.
            if not width or not height:
                width = 128
                height = 128
                if image:
                    if image.size[0] <= 128 and image.size[1] <= 128:
                        width = image.size[0]
                        height = image.size[1]
                    else:
                        image = None
                        self.report({'WARNING'}, 'Image texture must be 128x128 or smaller. Ignoring texture export.')


            # Print mesh header.
            # name, location, rotation is unused.
            output += '{\n'
            output += ' name=\'{}\', pos={{{},{},{}}}, rot={{0,0,0}},\n'.format(name, location[0], location[1], location[2])

            # Print the vertices.
            output += ' v={\n'
            object.rotation_mode = 'QUATERNION'
            # TODO:
            # The axes in picocad are a bit swapped from blender, compensation with a rotaion.
            # This requires updating position too.
            rotation = object.rotation_quaternion * Euler((0, 0, 0), 'XYZ').to_quaternion()
            for v in data.vertices:
                # Picocad does not support object rotation or scale so we bake them into the vertices.
                vertex = Vector((v.co[0], v.co[1], v.co[2]))
                vertex.rotate(rotation)
                vertex *= object.scale
                output += '  {{{:.1f},{:.1f},{:.1f}}},\n'.format(vertex[0], vertex[1], vertex[2])

            # Remove the trailing comma from the last line.
            output = output[:-2] + '\n'
            output += ' },\n'

            # Print the face header.
            output += ' f={\n'
            for f in data.polygons:
                # Optional parameters are: dbl=1, noshade=1, notex=1, prio=1
                output += '  {{{}, '.format(','.join(str(v + 1) for v in f.vertices))
                if double_sided:
                    output += 'dbl=1, '

                # Set the face color.
                output += 'c={}, '.format(mesh_color)
                if len(object.data.uv_layers) > 0:
                    output += 'uv={'
                    for loop_idx in f.loop_indices:
                        uv = object.data.uv_layers.active.data[loop_idx].uv
                        # Texture coordinates in picocad are in divisions of 8.
                        u = uv.x * width / 8
                        v = uv.y * height / 8
                        output += '{:.1f},{:.1f},'.format(u, v)
                    # Remove the trailing comma from the last line.
                    output = output[:-1]
                    output += '} },\n'
                else:
                    # There's no uvmap, just use 0s for every point.
                    output += 'uv={{{}}} }},\n'.format(','.join('0,0' for v in f.vertices))

            # Remove the trailing comma from the last line.
            output = output[:-2] + '\n'
            output += ' }\n'

            output += '},\n'

        # Remove the trailing comma from the last line.
        output = output[:-2] + '\n'
        output += '}%\n'

        # Convert the image to a picocad texture.
        if image:
            texture = ''
            column_count = 0
            column = ''
            for i in range(0, len(image.pixels), 4):
                r = image.pixels[i]
                g = image.pixels[i + 1]
                b = image.pixels[i + 2]
                # Ignore alpha.
                color = color_to_picocad_color(Color((r, g, b)))
                column += color
                column_count += 1
                if column_count == 128:
                    column_count = 0
                    texture += column[::-1] + '\n'
                    column = ''
            # Remove the trailing new line from the last line.
            texture = texture[:-1]
            # Invert the texture, for some reason it's upsidedown.
            output += texture[::-1]
        else:
            # If no texture image was supplied, use the default.
            output += DEFAULT_TEXTURE

        with open(self.filepath, 'w') as f:
            f.write(output)

        return {'FINISHED'}


# Create a mapping of picocad index, to picocad hex color and rgb color.
# Store the hex values as strings since they are going to saved in text anyway.
COLOR_MAP = [
    ('0', Color((0, 0, 0))), # Black
    ('1', Color((0.012286489829421043, 0.024157628417015076, 0.08650047332048416))), # Dark Blue
    ('2', Color((0.20863690972328186, 0.01850022003054619, 0.08650047332048416))), # Violet
    ('3', Color((0.0, 0.24228115379810333, 0.08228270709514618))), # Dark Green
    ('4', Color((0.40724021196365356, 0.08437623083591461, 0.0368894599378109))), # Brown
    ('5', Color((0.11443537473678589, 0.09530746936798096, 0.07818741351366043))), # Dark Gray
    ('6', Color((0.539479672908783, 0.5457245707511902, 0.5711249709129333))), # Light Gray
    ('7', Color((1.0, 0.8796226382255554, 0.8069523572921753))), # White
    ('8', Color((1.0, 0.0, 0.07421357929706573))), # Red
    ('9', Color((1.0, 0.3662526309490204, 0.0))), # Orange
    ('a', Color((1.0, 0.8387991189956665, 0.020288560539484024))), # Yellow
    ('b', Color((0.0, 0.7758224010467529, 0.0368894599378109))), # Light Green
    ('c', Color((0.022173885256052017, 0.4178851246833801, 1.0))), # Light Blue
    ('d', Color((0.22696588933467865, 0.18116429448127747, 0.33245155215263367))), # Gray Blue
    ('e', Color((1.0, 0.18447501957416534, 0.3915724754333496))), # Pink
    ('f', Color((1.0, 0.6038274168968201, 0.40197786688804626))) # Tan
]


# Cache to speed up lookups of the same color.
COLOR_CACHE = dict()


def color_distance(color1, color2):
    # Return how different these colors are based on Euclidian distance.
    return sqrt((color2.r - color1.r) ** 2 + (color2.g - color1.g) ** 2 + (color2.b - color1.b) ** 2)


def color_to_picocad(color):
    # There are 16 colors in picocad.
    # They are defined by either a single character, in the case of textures, or an index in the case of mesh color, background color, and transparency selection.
    # Find the closest color to a picocad color and return it.
    color_hash = (color.r, color.g, color.b)
    if color_hash in COLOR_CACHE.keys():
        return COLOR_CACHE[color_hash]

    min_dist = float('inf')
    closest_color_index = 0
    closest_color = 0
    for i, (pico, rgb) in enumerate(COLOR_MAP):
        dist = color_distance(color, rgb)
        if dist < min_dist:
            min_dist = dist
            closest_color_index = i
            closest_color = pico

    COLOR_CACHE[color_hash] = (closest_color_index, closest_color)
    return (closest_color_index, closest_color)


def color_to_picocad_index(color):
    return color_to_picocad(color)[0]


def color_to_picocad_color(color):
    return color_to_picocad(color)[1]


# This is the default grid texture that picocad uses.
DEFAULT_TEXTURE = '''00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
00000000eeee8888eeee8888aaaa9999aaaa9999bbbb3333bbbb3333ccccddddccccddddffffeeeeffffeeee7777666677776666555566665555666600000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
000000008888eeee8888eeee9999aaaa9999aaaa3333bbbb3333bbbbddddccccddddcccceeeeffffeeeeffff6666777766667777666655556666555500000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'''


def menu_func_export(self, context):
    self.layout.operator(PicocadExporter.bl_idname, text='Picocad')


def register():
    bpy.utils.register_class(PicocadExporter)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(PicocadExporter)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == '__main__':
    register()