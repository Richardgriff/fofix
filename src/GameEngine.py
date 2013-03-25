#####################################################################
# -*- coding: iso-8859-1 -*-                                        #
#                                                                   #
# Frets on Fire                                                     #
# Copyright (C) 2006 Sami Ky�stil�                                  #
#               2008 Alarian                                        #
#               2008 myfingershurt                                  #
#               2008 Glorandwarf                                    #
#               2008 Spikehead777                                   #
#               2008 QQStarS                                        #
#               2008 Blazingamer                                    #
#               2008 evilynux <evilynux@gmail.com>                  #
#               2008 fablaculp                                      #
#                                                                   #
# This program is free software; you can redistribute it and/or     #
# modify it under the terms of the GNU General Public License       #
# as published by the Free Software Foundation; either version 2    #
# of the License, or (at your option) any later version.            #
#                                                                   #
# This program is distributed in the hope that it will be useful,   #
# but WITHOUT ANY WARRANTY; without even the implied warranty of    #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the     #
# GNU General Public License for more details.                      #
#                                                                   #
# You should have received a copy of the GNU General Public License #
# along with this program; if not, write to the Free Software       #
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,        #
# MA  02110-1301, USA.                                              #
#####################################################################

import OpenGL
from OpenGL.GL import *
import numpy as np
from PIL import Image
import pygame
import gc
import os
import sys
import imp

from Video import Video
from Audio import Audio
from View import View
from Input import Input, KeyListener, SystemEventListener
from Resource import Resource
from Data import Data
from World import World
from Svg import SvgContext, ImgDrawing
#alarian
#from Song import EAS_DIF, MED_DIF, HAR_DIF, EXP_DIF
from Debug import DebugLayer
from Language import _
import Log
import Config
import Dialogs
from Theme import Theme
import Version
import Mod
import Player
from Shader import shaders
from constants import *
from TaskEngine import TaskEngine

import cmgl

# evilynux - Grab name and version from Version class.
version = "%s v%s" % ( Version.PROGRAM_NAME, Version.version() )

# define configuration keys
import ConfigDefs

##Alarian: Get unlimited themes by foldername
themepath = os.path.join(Version.dataPath(), "themes")
themes = []
defaultTheme = None           #myfingershurt
allthemes = os.listdir(themepath)
for name in allthemes:
    if os.path.exists(os.path.join(themepath,name,"notes","notes.png")):
        themes.append(name)
        if name == "MegaLight V4":
            defaultTheme = name

i = len(themes)
if i == 0:
    if os.name == 'posix':
        Log.error("No valid theme found!\n"+\
                  "Make sure theme files are properly cased "+\
                  "e.g. notes.png works, Notes.png doesn't\n")
    else:
        Log.error("No valid theme found!")
    sys.exit(1);

if defaultTheme is None:
    defaultTheme = themes[0]    #myfingershurt

#myfingershurt: default theme must be an existing one!
Config.define("coffee", "themename",           str,   defaultTheme,      text = _("Theme"),                options = dict([(str(themes[n]),themes[n]) for n in range(0, i)]), tipText = _("Sets the overall graphical feel of the game. You can find and download many more at fretsonfire.net"))

##Alarian: End Get unlimited themes by foldername
Player.loadControls()



class FullScreenSwitcher(KeyListener):
    """
    A keyboard listener that looks for special built-in key combinations,
    such as the fullscreen toggle (Alt-Enter).
    """
    def __init__(self, engine):
        self.engine = engine
        self.altStatus = False

    def keyPressed(self, key, unicode):
        if key == pygame.K_LALT:
            self.altStatus = True
        elif key == pygame.K_RETURN and self.altStatus:
            if not self.engine.toggleFullscreen():
                Log.error("Unable to toggle fullscreen mode.")
            return True
        elif key == pygame.K_d and self.altStatus:
            self.engine.setDebugModeEnabled(not self.engine.isDebugModeEnabled())
            return True
        elif key == pygame.K_g and self.altStatus and self.engine.isDebugModeEnabled():
            self.engine.debugLayer.gcDump()
            return True

    def keyReleased(self, key):
        if key == pygame.K_LALT:
            self.altStatus = False

class SystemEventHandler(SystemEventListener):
    """
    A system event listener that takes care of restarting the game when needed
    and reacting to screen resize events.
    """
    def __init__(self, engine):
        self.engine = engine

    def screenResized(self, size):
        self.engine.resizeScreen(size[0], size[1])

    def restartRequested(self):
        self.engine.restart()

    def quit(self):
        self.engine.quit()

class GameEngine(object):
    """The main game engine."""
    def __init__(self, config = None):

        Log.debug("GameEngine class init (GameEngine.py)...")
        self.mainMenu = None    #placeholder for main menu object - to prevent reinstantiation

        self.currentScene = None

        self.versionString = version  #stump: other version stuff moved to allow full version string to be retrieved without instantiating GameEngine
        self.uploadVersion = "%s-4.0" % Version.PROGRAM_NAME #akedrou - the version passed to the upload site.

        self.dataPath = Version.dataPath()
        Log.debug(self.versionString + " starting up...")
        Log.debug("Python version: " + sys.version.split(' ')[0])
        Log.debug("Pygame version: " + str(pygame.version.ver) )
        Log.debug("PyOpenGL version: " + OpenGL.__version__)
        Log.debug("Numpy version: " + np.__version__)
        Log.debug("PIL version: " + Image.VERSION)
        Log.debug("sys.argv: " + repr(sys.argv))
        Log.debug("os.name: " + os.name)
        Log.debug("sys.platform: " + sys.platform)
        if os.name == 'nt':
            import win32api
            Log.debug("win32api.GetVersionEx(1): " + repr(win32api.GetVersionEx(1)))
        elif os.name == 'posix':
            Log.debug("os.uname(): " + repr(os.uname()))

        """
        Constructor.
        @param config:  L{Config} instance for settings
        """

        self.tutorialFolder = "tutorials"

        if not config:
            config = Config.load()

        self.config  = config

        fps          = self.config.get("video", "fps")
        self.fps = fps
        self.running = True
        self.clock = pygame.time.Clock()
        self.task = TaskEngine(self)
        
        # Compatiblity task management
        self.addTask = self.task.addTask
        self.removeTask = self.task.removeTask
        self.pauseTask = self.task.pauseTask
        self.resumeTask = self.task.resumeTask

        self.title             = self.versionString
        self.restartRequested  = False

        # evilynux - Check if theme icon exists first, then fallback on FoFiX icon.
        themename = self.config.get("coffee", "themename")
        themeicon = os.path.join(Version.dataPath(), "themes", themename, "icon.png")
        fofixicon = os.path.join(Version.dataPath(), "fofix_icon.png")
        icon = None
        if os.path.exists(themeicon):
            icon = themeicon
        elif os.path.exists(fofixicon):
            icon = fofixicon

        self.video             = Video(self.title, icon)
        if self.config.get("video", "disable_screensaver"):
            self.video.disableScreensaver()

        self.audio             = Audio()
        self.frames            = 0
        self.fpsEstimate       = 0
        self.priority          = self.config.get("engine", "highpriority")
        self.show_fps          = self.config.get("video", "show_fps")
        self.advSettings       = self.config.get("game", "adv_settings")
        self.restartRequired   = False
        self.quicksetRestart   = False
        self.quicksetPerf      = self.config.get("quickset", "performance")
        self.scrollRate        = self.config.get("game", "scroll_rate")
        self.scrollDelay       = self.config.get("game", "scroll_delay")

        Log.debug("Initializing audio.")
        frequency    = self.config.get("audio", "frequency")
        bits         = self.config.get("audio", "bits")
        stereo       = self.config.get("audio", "stereo")
        bufferSize   = self.config.get("audio", "buffersize")
        self.audio.open(frequency = frequency, bits = bits, stereo = stereo, bufferSize = bufferSize)

        self.cmdPlay           = 0
        self.cmdMode           = None
        self.cmdDiff           = None
        self.cmdPart           = None

        self.gameStarted       = False
        self.world             = None

        self.audioSpeedFactor  = 1.0

        Log.debug("Initializing video.")
        #myfingershurt: ensuring windowed mode starts up in center of the screen instead of cascading positions:
        os.environ['SDL_VIDEO_WINDOW_POS'] = 'center'

        width, height = [int(s) for s in self.config.get("video", "resolution").split("x")]
        fullscreen    = self.config.get("video", "fullscreen")
        multisamples  = self.config.get("video", "multisamples")
        self.video.setMode((width, height), fullscreen = fullscreen, multisamples = multisamples)
        Log.debug("OpenGL version: " + glGetString(GL_VERSION))
        Log.debug("OpenGL vendor: " + glGetString(GL_VENDOR))
        Log.debug("OpenGL renderer: " + glGetString(GL_RENDERER))
        Log.debug("OpenGL extensions: " + ' '.join(sorted(glGetString(GL_EXTENSIONS).split())))

        if self.video.default:
            self.config.set("video", "fullscreen", False)
            self.config.set("video", "resolution", "800x600")

        if self.config.get("video", "shader_use"):
            shaders.set(os.path.join(Version.dataPath(), "shaders"))

        # Enable the high priority timer if configured
        if self.priority:
            Log.debug("Enabling high priority timer.")
            self.fps = 0 # High priority

        # evilynux - This was generating an error on the first pass (at least under
        #            GNU/Linux) as the Viewport was not set yet.
        try:
            viewport = glGetIntegerv(GL_VIEWPORT)
        except:
            viewport = [0, 0, width, height]
        h = viewport[3] - viewport[1]
        w = viewport[2] - viewport[0]
        geometry = (0, 0, w, h)
        self.svg = SvgContext(geometry)
        glViewport(int(viewport[0]), int(viewport[1]), int(viewport[2]), int(viewport[3]))

        self.startupMessages   = self.video.error
        self.input     = Input()
        self.view      = View(self, geometry)
        self.resizeScreen(w, h)

        self.resource  = Resource(Version.dataPath())
        self.mainloop  = self.loading
        self.menuMusic = False

        self.setlistMsg = None


        # Load game modifications
        Mod.init(self)
        self.task.addTask(self.input, synced = False)

        self.task.addTask(self.view, synced = False)

        self.task.addTask(self.resource, synced = False)

        self.data = Data(self.resource, self.svg)

        ##MFH: Animated stage folder selection option
        #<themename>\Stages still contains the backgrounds for when stage rotation is off, and practice.png
        #subfolders under Stages\ will each be treated as a separate animated stage set

        self.stageFolders = []
        currentTheme = themename

        stagespath = os.path.join(Version.dataPath(), "themes", currentTheme, "backgrounds")
        themepath  = os.path.join(Version.dataPath(), "themes", currentTheme)
        if os.path.exists(stagespath):
            self.stageFolders = []
            allFolders = os.listdir(stagespath)   #this also includes all the stage files - so check to see if there is at least one .png file inside each folder to be sure it's an animated stage folder
            for name in allFolders:
                aniStageFolderListing = []
                thisIsAnAnimatedStageFolder = False
                try:
                    aniStageFolderListing = os.listdir(os.path.join(stagespath,name))
                except Exception:
                    thisIsAnAnimatedStageFolder = False
                for aniFile in aniStageFolderListing:
                    if os.path.splitext(aniFile)[1] == ".png" or os.path.splitext(aniFile)[1] ==  ".jpg" or os.path.splitext(aniFile)[1] == ".jpeg":  #we've found at least one .png file here, chances are this is a valid animated stage folder
                        thisIsAnAnimatedStageFolder = True
                if thisIsAnAnimatedStageFolder:
                    self.stageFolders.append(name)


            i = len(self.stageFolders)
            if i > 0: #only set default to first animated subfolder if one exists - otherwise use Normal!
                defaultAniStage = str(self.stageFolders[0])
            else:
                defaultAniStage = "Normal"
            Log.debug("Default animated stage for " + currentTheme + " theme = " + defaultAniStage)
            aniStageOptions = dict([(str(self.stageFolders[n]),self.stageFolders[n]) for n in range(0, i)])
            aniStageOptions.update({"Normal":_("Slideshow")})
            if i > 1:   #only add Random setting if more than one animated stage exists
                aniStageOptions.update({"Random":_("Random")})
            Config.define("game", "animated_stage_folder", str, defaultAniStage, text = _("Animated Stage"), options = aniStageOptions )

            #MFH: here, need to track and check a new ini entry for last theme - so when theme changes we can re-default animated stage to first found
            lastTheme = self.config.get("game","last_theme")
            if lastTheme == "" or lastTheme != currentTheme:   #MFH - no last theme, and theme just changed:
                self.config.set("game","animated_stage_folder",defaultAniStage)   #force defaultAniStage
            self.config.set("game","last_theme",currentTheme)

            selectedAnimatedStage = self.config.get("game", "animated_stage_folder")
            if selectedAnimatedStage != "Normal" and selectedAnimatedStage != "Random":
                if not os.path.exists(os.path.join(stagespath,selectedAnimatedStage)):
                    Log.warn("Selected animated stage folder " + selectedAnimatedStage + " does not exist, forcing Normal.")
                    self.config.set("game","animated_stage_folder","Normal") #MFH: force "Standard" currently selected animated stage folder is invalid
        else:
            Config.define("game", "animated_stage_folder", str, "None", text = _("Animated Stage"), options = ["None",_("None")])
            Log.warn("No stages\ folder found, forcing None setting for Animated Stage.")
            self.config.set("game","animated_stage_folder", "None") #MFH: force "None" when Stages folder can't be found



        try:
            fp, pathname, description = imp.find_module("CustomTheme",[themepath])
            theme = imp.load_module("CustomTheme", fp, pathname, description)
            self.theme = theme.CustomTheme(themepath, themename)
        except ImportError:
            self.theme = Theme(themepath, themename)

        self.task.addTask(self.theme)


        self.input.addKeyListener(FullScreenSwitcher(self), priority = True)
        self.input.addSystemEventListener(SystemEventHandler(self))

        self.debugLayer         = None
        self.startupLayer       = None
        self.loadingScreenShown = False
        self.graphicMenuShown   = False

        Log.debug("Ready.")


    # evilynux - This stops the crowd cheers if they're still playing (issue 317).
    def quit(self):
        # evilynux - self.audio.close() crashes when we attempt to restart
        if not self.restartRequested:
            self.audio.close()
        Player.savePlayers()
        for taskData in list(self.task.tasks):
            self.task.removeTask(taskData['task'])
        self.running = False

    def setStartupLayer(self, startupLayer):
        """
        Set the L{Layer} that will be shown when the all
        the resources have been loaded. See L{Data}

        @param startupLayer:    Startup L{Layer}
        """
        self.startupLayer = startupLayer

    def isDebugModeEnabled(self):
        return bool(self.debugLayer)

    def setDebugModeEnabled(self, enabled):
        """
        Show or hide the debug layer.

        @type enabled: bool
        """
        if enabled:
            self.debugLayer = DebugLayer(self)
        else:
            self.debugLayer = None

    def toggleFullscreen(self):
        """
        Toggle between fullscreen and windowed mode.

        @return: True on success
        """
        if not self.video.toggleFullscreen():
            # on windows, the fullscreen toggle kills our textures, se we must restart the whole game
            self.input.broadcastSystemEvent("restartRequested")
            self.config.set("video", "fullscreen", not self.video.fullscreen)
            return True
        self.config.set("video", "fullscreen", self.video.fullscreen)
        return True

    def restart(self):
        """Restart the game."""
        if not self.restartRequested:
            self.restartRequested = True
            self.input.broadcastSystemEvent("restartRequested")
        else:
            self.quit()

    def resizeScreen(self, width, height):
        """
        Resize the game screen.

        @param width:   New width in pixels
        @param height:  New height in pixels
        """
        self.view.setGeometry((0, 0, width, height))
        self.svg.setGeometry((0, 0, width, height))

    def startWorld(self, players, maxplayers = None, gameMode = 0, multiMode = 0, allowGuitar = True, allowDrum = True, allowMic = False, tutorial = False):
        self.world = World(self, players, maxplayers, gameMode, multiMode, allowGuitar, allowDrum, allowMic, tutorial)

    def finishGame(self):
        if not self.world:
            Log.notice("GameEngine.finishGame called before World created.")
            return
        self.world.finishGame()
        self.world = None
        self.gameStarted = False
        self.view.pushLayer(self.mainMenu)

    def loadImgDrawing(self, target, name, fileName, textureSize = None):
        """
        Load an SVG drawing synchronously.

        @param target:      An object that will own the drawing
        @param name:        The name of the attribute the drawing will be assigned to
        @param fileName:    The name of the file in the data directory
        @param textureSize: Either None or (x, y), in which case the file will
                            be rendered to an x by y texture
        @return:            L{ImgDrawing} instance
        """
        return self.data.loadImgDrawing(target, name, fileName, textureSize)

    #volshebnyi
    def drawStarScore(self, screenwidth, screenheight, xpos, ypos, stars, scale = None, horiz_spacing = 1.2, space = 1.0, hqStar = False, align = LEFT):
        minScale = 0.02
        w = screenwidth
        h = screenheight
        if not scale:
            scale = minScale
        elif scale < minScale:
            scale = minScale
        if self.data.fcStars and stars == 7:
            star = self.data.starFC
        else:
            star = self.data.starPerfect
        wide = scale * horiz_spacing
        if align == CENTER: #center - akedrou (simplifying the alignment...)
            xpos  -= (2 * wide)
        elif align == RIGHT: #right
            xpos  -= (4 * wide)
        if stars > 5:
            for j in range(5):

                if self.data.maskStars:
                    if self.data.theme == 2:
                        self.drawImage(star, scale = (scale,-scale), coord = (w*(xpos+wide*j)*space**4,h*ypos), color = (1, 1, 0, 1), stretched = KEEP_ASPECT | FIT_WIDTH)
                    else:
                        self.drawImage(star, scale = (scale,-scale), coord = (w*(xpos+wide*j)*space**4,h*ypos), color = (0, 1, 0, 1), stretched = KEEP_ASPECT | FIT_WIDTH)
                else:
                    self.drawImage(star, scale = (scale,-scale), coord = (w*(xpos+wide*j)*space**4,h*ypos), stretched = KEEP_ASPECT | FIT_WIDTH)
        else:
            for j in range(5):
                if j < stars:
                    if hqStar:
                        star = self.data.star4
                    else:
                        star = self.data.star2
                else:
                    if hqStar:
                        star = self.data.star3
                    else:
                        star = self.data.star1
                self.drawImage(star, scale = (scale,-scale), coord = (w*(xpos+wide*j)*space**4,h*ypos), stretched = KEEP_ASPECT | FIT_WIDTH)

    def drawImage(self, image, scale = (1.0, -1.0), coord = (0, 0), rot = 0, \
                  color = (1,1,1,1), rect = (0,1,0,1), stretched = 0, fit = CENTER, \
                  alignment = CENTER, valignment = MIDDLE):
        """
        Draws the image/surface to screen
        @depreciated please use the specific methods of the image or Im.drawImage

        @param image:        The openGL surface
        @param scale:        Scale factor (between 0.0 and 1.0, second value must be negative due to texture flipping)
        @param coord:        Where the image will be translated to on the screen
        @param rot:          How many degrees it will be rotated
        @param color:        The color of the image
                                 (values are between 0.0 and 1.0)
                                 (can have 3 values or 4, if 3 are given the alpha is automatically set to 1.0)
        @param rect:         The surface rectangle, this is used for cropping the texture

                             Any other values will have the image maintain its size passed by scale
        @param alignment:    Adjusts the texture so the coordinate for x-axis placement can either be
                             on the left side (0), center point (1), or right(2) side of the image
        @param valignment:   Adjusts the texture so the coordinate for y-axis placement can either be
                             on the bottom side (0), center point (1), or top(2) side of the image
        """

        return ImgDrawing.drawImage(image, scale, coord, rot, color, rect, stretched, fit, alignment, valignment)

    #blazingamer
    def draw3Dtex(self, image, vertex, texcoord, coord = None, scale = None, rot = None, color = (1,1,1), multiples = False, alpha = False, depth = False, vertscale = 0):
        '''
        Simplifies tex rendering

        @param image: self.xxx - tells the system which image/resource should be mapped to the plane
        @param vertex: (Left, Top, Right, Bottom) - sets the points that define where the plane will be drawn
        @param texcoord: (Left, Top, Right, Bottom) - sets where the texture should be drawn on the plane
        @param coord: (x,y,z) - where on the screen the plane will be rendered within the 3d field
        @param scale: (x,y,z) - scales an glplane how far in each direction

        @param rot: (degrees, x-axis, y-axis, z-axis)
        a digit in the axis is how many times you want to rotate degrees around that axis

        @param color: (r,g,b) - sets the color of the image when rendered
        0 = No Color, 1 = Full color

        @param multiples: True/False
        defines whether or not there should be multiples of the plane drawn at the same time
        only really used with the rendering of the notes, keys, and flames

        @param alpha: True/False - defines whether or not the image should have black turned into transparent
        only really used with hitglows and flames

        @param depth: True/False - sets the depth by which the object is rendered
        only really used by keys and notes

        @param vertscale: # - changes the yscale when setting vertex points
        only really used by notes
        '''


        if not isinstance(image, ImgDrawing):
            return

        if alpha == True:
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        if len(color) == 4:
            col_array  = np.array([[color[0],color[1],color[2], color[3]],
                               [color[0],color[1],color[2], color[3]],
                               [color[0],color[1],color[2], color[3]],
                               [color[0],color[1],color[2], color[3]]], dtype=np.float32)
        else:
            col_array  = np.array([[color[0],color[1],color[2], 1],
                               [color[0],color[1],color[2], 1],
                               [color[0],color[1],color[2], 1],
                               [color[0],color[1],color[2], 1]], dtype=np.float32)

        glEnable(GL_TEXTURE_2D)
        image.texture.bind()

        if multiples == True:
            glPushMatrix()

        if coord != None:
            glTranslate(coord[0], coord[1], coord[2])
        if rot != None:
            glRotate(rot[0], rot[1], rot[2], rot[3])
        if scale != None:
            glScalef(scale[0], scale[1], scale[2])

        if depth == True:
            glDepthMask(1)

        if not isinstance(vertex, np.ndarray):
            vertex = np.array(
              [[ vertex[0],  vertscale, vertex[1]],
               [ vertex[2],  vertscale, vertex[1]],
               [ vertex[0], -vertscale, vertex[3]],
               [ vertex[2], -vertscale, vertex[3]]], dtype=np.float32)

        if not isinstance(texcoord, np.ndarray):
            texcoord = np.array(
              [[texcoord[0], texcoord[1]],
               [texcoord[2], texcoord[1]],
               [texcoord[0], texcoord[3]],
               [texcoord[2], texcoord[3]]], dtype=np.float32)

        cmgl.drawArrays(GL_TRIANGLE_STRIP, vertices=vertex, colors=col_array, texcoords=texcoord)

        if depth == True:
            glDepthMask(0)

        if multiples == True:
            glPopMatrix()

        glDisable(GL_TEXTURE_2D)

        if alpha == True:
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    
    #glorandwarf: renamed to retrieve the path of the file
    def fileExists(self, fileName):
        return self.data.fileExists(fileName)

    def getPath(self, fileName):
        return self.data.getPath(fileName)

    def loading(self):
        """Loading state loop."""
        done = self.task.run()
        self.clearScreen()

        if self.data.essentialResourcesLoaded():
            if not self.loadingScreenShown:
                self.loadingScreenShown = True
                Dialogs.showLoadingScreen(self, self.data.resourcesLoaded)
                if self.startupLayer:
                    self.view.pushLayer(self.startupLayer)
                self.mainloop = self.main
            self.view.render()
        self.video.flip()
        return done

    def clearScreen(self):
        self.svg.clear(*self.theme.backgroundColor)

    def fadeScreen(self, v):
        """
        Fade the screen to a dark color to make whatever is on top easier to read.

        @param v: Visibility factor [0..1], 0 is fully visible
        """
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_COLOR_MATERIAL)

        glBegin(GL_TRIANGLE_STRIP)
        glColor4f(0, 0, 0, .3 - v * .3)
        glVertex2f(0, 0)
        glColor4f(0, 0, 0, .3 - v * .3)
        glVertex2f(1, 0)
        glColor4f(0, 0, 0, .9 - v * .9)
        glVertex2f(0, 1)
        glColor4f(0, 0, 0, .9 - v * .9)
        glVertex2f(1, 1)
        glEnd()

    def enableGarbageCollection(self, enabled):
        """
        Enable or disable garbage collection whenever a random garbage
        collection run would be undesirable. Disabling the garbage collector
        has the unfortunate side-effect that your memory usage will skyrocket.
        """
        if enabled:
            gc.enable()
        else:
            gc.disable()

    def collectGarbage(self):
        """
        Run a garbage collection run.
        """
        gc.collect()

    def main(self):
        """Main state loop."""
        done = self.task.run()
        self.clearScreen()
        self.view.render()
        if self.debugLayer:
            self.debugLayer.render(1.0, True)
        self.video.flip()
        
        # evilynux - Estimate the rendered frames per second.
        self.frames = self.frames+1
        # Estimate every 120 frames when highpriority is True.
        # Estimate every 2*config.fps when highpriority is False,
        # if you are on target, that should be every 2 seconds.
        if( not self.priority and self.frames == (self.fps << 1) ) or ( self.priority and self.frames == 120 ):
            self.fpsEstimate = self.clock.get_fps()
            # evilynux - Printing on the console with a frozen binary may cause a crash.
            if self.show_fps and not Version.isWindowsExe():
                print("%.2f fps" % self.fpsEstimate)
            self.frames = 0
        
        return done

    def run(self):
        return self.mainloop()
