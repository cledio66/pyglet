#!/usr/bin/env python

'''

Image loading is performed by OS components we believe we can rely on.

We ONLY support PNG and JPEG formats, thus enforcing that we only load the
formats we have base support for.

Linux (in order of preference):

   PNG:   libpng           (will ABORT program if PNG is corrupted)
   PNG:   libjpeg

   Fallbacks: GTK? Qt? SDL?

Windows:

   PNG:    ??
   JPEG:   ??

OS X:

   PNG:    libpng
   JPEG:   ??

'''

__docformat__ = 'restructuredtext'
__version__ = '$Id$'

import sys
import re

from ctypes import *

from pyglet.GL.VERSION_1_1 import *

if sys.platform == 'win32':
    png = jpeg = None
elif sys.platform == 'darwin':
    from pyglet.image import png
    jpeg = None
else:
    from pyglet.image import png
    from pyglet.image import jpeg

# XXX include the image filename in the args? might help debugging?
class Image(object):
    def __init__(self, data, width, height, bpp):
        self.data = data
        self.width = width
        self.height = height
        self.bpp = bpp

    @classmethod
    def load(cls, filename):
        if re.match(r'.*?\.png$', filename, re.I):
            if png is None:
                raise ValueError, "Can't load PNG images"
            return png.read(filename)
        if re.match(r'.*?\.jpe?g$', filename, re.I):
            if jpeg is None:
                raise ValueError, "Can't load JPEG images"
            return jpeg.read(filename)
        if png is not None and png.is_png(filename):
            return png.read(filename)
        if jpeg is not None and jpeg.is_jpeg(filename):
            return jpeg.read(filename)
        raise ValueError, 'File is not a PNG or JPEG'

    def as_texture(self):
        return Texture.from_image(self)

def _nearest_pow2(n):
    i = 1
    while i < n:
        i <<= 1
    return i

def _get_texture_from_surface(surface):
    if surface.format.BitsPerPixel != 24 and \
       surface.format.BitsPerPixel != 32:
        raise AttributeError('Unsupported surface format')
    return _get_texture(surface.pixels.to_string(), surface.w, surface.h,
        surface.format.BytesPerPixel)

def _get_texture(data, width, height, bpp):
    # XXX get from config...
    # XXX determine max texture size
    # XXX test whether the hardware can cope with non-^2 texture sizes
    # XXX test whether the hardware can cope with non-square textures
    tex_width = tex_height = max(_nearest_pow2(width), _nearest_pow2(height))
    uv = (float(width) / tex_width, float(height) / tex_height)

    if bpp == 2: iformat = format = GL_LUMINANCE_ALPHA
    elif bpp == 3: iformat = format = GL_RGB
    else: iformat = format = GL_RGBA

    id = c_uint()
    glGenTextures(1, byref(id))
    id = id.value
    glBindTexture(GL_TEXTURE_2D, id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    if tex_width == width and tex_height == height:
        glTexImage2D(GL_TEXTURE_2D, 0, iformat, tex_width, tex_height, 0,
            format, GL_UNSIGNED_BYTE, data)
    else:
        blank = '\0' * tex_width * tex_height * bpp
        glTexImage2D(GL_TEXTURE_2D, 0, iformat, tex_width, tex_height, 0,
            format, GL_UNSIGNED_BYTE, blank)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, format,
            GL_UNSIGNED_BYTE, data)

    return id, uv

class Texture(object):
    def __init__(self, id, width, height, uv):
        self.id = id
        self.width, self.height = width, height
        self.uv = uv

        # Make quad display list
        self.quad_list = glGenLists(1)
        glNewList(self.quad_list, GL_COMPILE)
        glBindTexture(GL_TEXTURE_2D, self.id)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(0, 0)
        glTexCoord2f(0, self.uv[1])
        glVertex2f(0, self.height)
        glTexCoord2f(self.uv[0], self.uv[1])
        glVertex2f(self.width, self.height)
        glTexCoord2f(self.uv[0], 0)
        glVertex2f(self.width, 0)

        glEnd()
        glEndList()

    def draw(self):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_list)
        glPopAttrib()

    @classmethod
    def from_data(cls, data, width, height, bpp):
        id, uv = _get_texture(data, width, height, bpp)
        return Texture(id, width, height, uv)

    @classmethod
    def from_image(cls, image):
        id, uv = _get_texture(image.data, image.width, image.height,
            image.bpp)
        return Texture(id, image.width, image.height, uv)

    @classmethod
    def from_surface(cls, surface):
        id, uv = _get_texture_from_surface(surface)
        return Texture(id, surface.w, surface.h, uv)


class AtlasSubTexture(object):
    def __init__(self, quad_list, width, height, uv):
        self.quad_list = quad_list
        self.width, self.height = width, height
        self.uv = uv

    def draw(self):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_list)
        glPopAttrib()

class TextureAtlasRects(object):
    def __init__(self, id, width, height, uv, rects):
        self.size = (width, height)
        self.id = id
        self.uvs = []
        self.quad_lists = []
        self.elem_sizes = []

        n = glGenLists(len(rects))
        self.quad_lists = range(n, n + len(rects))
        for i, rect in enumerate(rects):
            u = float(rect[0]) / width * uv[0]
            v = float(rect[1]) / height * uv[1]
            du = float(rect[2]) / width * uv[0]
            dv = float(rect[3]) / height * uv[1]
            elem_uv = (u, v, u + du, v + dv)
            elem_size = (rect[2], rect[3])

            glNewList(self.quad_lists[i], GL_COMPILE)
            glBindTexture(GL_TEXTURE_2D, self.id)
            glBegin(GL_QUADS)
            glTexCoord2f(u, v)
            glVertex2f(0, 0)
            glTexCoord2f(u + du, v)
            glVertex2f(elem_size[0], 0)
            glTexCoord2f(u + du, v + dv)
            glVertex2f(elem_size[0], elem_size[1])
            glTexCoord2f(u, v + dv)
            glVertex2f(0, elem_size[1])
            glEnd()
            glEndList()

            self.uvs.append(elem_uv)
            self.elem_sizes.append(elem_size)

    @classmethod
    def from_data(cls, data, width, height, bpp, rects=[]):
        id, uv = _get_texture(data, width, height, bpp)
        return cls(id, width, height, uv, rects)

    @classmethod
    def from_image(cls, image, rects=[]):
        id, uv = _get_texture(image.data, image.width, image.height,
            image.bpp)
        return cls(id, image.width, image.height, uv, rects)

    @classmethod
    def from_surface(cls, surface, rects=[]):
        id, uv = _get_texture_from_surface(surface)
        return cls(id, surface.w, surface.h, uv, rects)

    def draw(self, index):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_lists[index])
        glPopAttrib()

    def get_size(self, index):
        return self.elem_sizes[index]

    def get_quad(self, index):
        return self.elem_sizes[index], self.uvs[index]

    def get_texture(self, index):
        '''Return something that smells like a Texture instance.'''
        w, h = self.elem_sizes[index]
        return AtlasSubTexture(self.quad_lists[index], w, h, self.uvs[index])


class TextureAtlasGrid(object):
    def __init__(self, id, width, height, uv, rows=1, cols=1):
        assert rects or (rows >= 1 and cols >= 1)
        self.size = (width, height)
        self.id = id
        self.uvs = []
        self.quad_lists = []
        self.elem_sizes = []

        self.rows = rows
        self.cols = cols

        elem_size = width / cols, height / rows
        n = glGenLists(rows * cols)
        self.quad_lists = range(n, n + rows * cols)
        du = uv[0] / cols
        dv = uv[1] / rows
        i = v = 0
        for row in range(rows):
            u = 0
            for col in range(cols):
                glNewList(self.quad_lists[i], GL_COMPILE)
                glBindTexture(GL_TEXTURE_2D, self.id)
                glBegin(GL_QUADS)
                glTexCoord2f(u, v)
                glVertex2f(0, 0)
                glTexCoord2f(u + du, v)
                glVertex2f(elem_size[0], 0)
                glTexCoord2f(u + du, v + dv)
                glVertex2f(elem_size[0], elem_size[1])
                glTexCoord2f(u, v + dv)
                glVertex2f(0, elem_size[1])
                glEnd()
                glEndList()

                elem_uv = (u, v, u + du, v + dv)
                self.uvs.append(elem_uv)
                self.elem_sizes.append(elem_size)
                u += du
                i += 1
            v += dv

    @classmethod
    def from_data(cls, data, width, height, bpp, rows=1, cols=1):
        id, uv = _get_texture(data, width, height, bpp)
        return cls(id, width, height, uv, rows, cols)

    @classmethod
    def from_image(cls, image, rows=1, cols=1):
        id, uv = _get_texture(image.data, image.width, image.height,
            image.bpp)
        return cls(id, image.width, image.height, uv, rows, cols)

    @classmethod
    def from_surface(cls, surface, rows=1, cols=1):
        id, uv = _get_texture_from_surface(surface)
        return cls(id, surface.w, surface.h, uv, rows, cols)

    def draw(self, row, col):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_lists[row * self.cols + col])
        glPopAttrib()

    def get_size(self, row, col):
        return self.elem_sizes[row * self.cols + col]

    def get_quad(self, row, col):
        i = row * self.cols + col
        return self.elem_sizes[i], self.uvs[i]

