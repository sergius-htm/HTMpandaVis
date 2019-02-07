# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

from direct.showbase.ShowBase import ShowBase
from panda3d.core import LColor
from panda3d.core import GeomVertexFormat, GeomVertexData, GeomVertexWriter,Geom,GeomLines,GeomNode,PerspectiveLens

from htm import cHTM 
from gui import cGUI

class cApp(ShowBase):
 
    FOCAL_LENGTH = 500
    
    def __init__(self):
        ShowBase.__init__(self)
        
        # Mouse and camera movement init
        self.mouseX_last=0
        self.mouseY_last=0
        self.rotateCamera=False
        self.move_z=50
        
    
        #self.CreateTestScene()
         

        self.SetupCameraAndKeys()

        self.taskMgr.add(self.update, 'main loop')
        
        self.accept(self.win.getWindowEvent(),self.onWindowEvent)
        
        
        self.gui = cGUI()
        
        self.htm = cHTM()
        
        self.htm.CreateGfx(self.loader)
        self.htm.getNode().reparentTo(self.render)
        

    def SetupCameraAndKeys(self):
        # Setup controls
        self.keys = {}
        for key in ['arrow_left', 'arrow_right', 'arrow_up', 'arrow_down',
                    'a', 'd', 'w', 's','shift','control']:
            self.keys[key] = 0
            self.accept(key, self.push_key, [key, 1])
            self.accept('shift-%s' % key, self.push_key, [key, 1])
            self.accept('%s-up' % key, self.push_key, [key, 0])
        
        self.accept('escape', __import__('sys').exit, [0])
        self.disableMouse()

        # Setup camera
        width = self.win.getProperties().getXSize()
        height = self.win.getProperties().getYSize()
        lens = PerspectiveLens()
        lens.setFov(60)

        lens.setAspectRatio(width/height)
        #lens.setFilmSize(width,height)
        #lens.setFocalLength(self.FOCAL_LENGTH)
        self.cam.node().setLens(lens)
        
        self.camera.setPos(40, -80, 0)
        self.heading = 0.0
        self.pitch = -30.0
        
        
        self.accept('mouse1',self.mouseEvent,["left",True])
        self.accept('mouse1-up',self.mouseEvent,["left",False])
        self.accept('mouse3',self.mouseEvent,["right",True])
        self.accept('mouse3-up',self.mouseEvent,["right",False])
        
    def onWindowEvent(self,window):
        width = self.win.getProperties().getXSize()
        height = self.win.getProperties().getYSize()
        
        lens = PerspectiveLens()
        lens.setFov(60)
        lens.setAspectRatio(width/height)
        
        
        #lens.setFilmSize(width,height)
        #lens.setFocalLength(self.FOCAL_LENGTH)
        self.cam.node().setLens(lens)
        
    def push_key(self, key, value):
        """Stores a value associated with a key."""
        self.keys[key] = value
        
    def mouseEvent(self, event,press):
        #print(event)
        if event=='right':
            self.rotateCamera=press
            
            if self.mouseWatcherNode.hasMouse():
                self.mouseX_last = self.mouseWatcherNode.getMouseX()
                self.mouseY_last = self.mouseWatcherNode.getMouseY()
            else:
                self.mouseX_last = 0
                self.mouseY_last = 0
            """if press:
                props = WindowProperties()
                props.setCursorHidden(True)
                props.setMouseMode(WindowProperties.M_relative)
                self.win.requestProperties(props)"""
                
        
    def update(self, task):
        """Updates the camera based on the keyboard input. Once this is
        done, then the CellManager's update function is called."""
        deltaT = globalClock.getDt()
        
        speed=20
        
        """Rotation with mouse while right-click"""
        mw = self.mouseWatcherNode
        deltaX=0
        deltaY=0
        
        if mw.hasMouse() and self.rotateCamera:
            deltaX = mw.getMouseX() - self.mouseX_last
            deltaY = mw.getMouseY() - self.mouseY_last
            
            
            self.mouseX_last = mw.getMouseX()
            self.mouseY_last = mw.getMouseY()        
        
        
        move_x = deltaT * speed * -self.keys['a'] + deltaT * speed * self.keys['d']
        move_y = deltaT * speed * self.keys['s'] + deltaT * speed * -self.keys['w']
        self.move_z += deltaT * speed * self.keys['shift'] + deltaT * speed * -self.keys['control']
        
        self.camera.setPos(self.camera,move_x, -move_y, 0)
        self.camera.setZ(self.move_z)
        
        self.heading += (deltaT * 90 * self.keys['arrow_left'] +
                         deltaT * 90 * -self.keys['arrow_right'] +
                         deltaT * 5000 * -deltaX)
        self.pitch += (deltaT * 90 * self.keys['arrow_up'] +
                       deltaT * 90 * -self.keys['arrow_down']+
                       deltaT * 5000 * deltaY)
        self.camera.setHpr(self.heading, self.pitch, 0)
        
        
        return task.cont
        
    
    def CreateTestScene(self):
        
        # Load the environment model.
        self.cube = self.loader.loadModel("cube")#/media/Data/Data/Panda3d/
        
        # Reparent the model to render.
        self.cube.reparentTo(self.render)
        # Apply scale and position transforms on the model.
        
        self.cube.setScale(10, 10, 10)
        self.cube.setPos(-8, 42, 0)
        
        self.cube.setColor(1.0,0,0,1.0)
        self.cube.setRenderModeThickness(5)
        
        self.cube.setRenderModeFilledWireframe(LColor(0,0,0,1.0))
        
        
        form = GeomVertexFormat.getV3()
        
        vdata = GeomVertexData('myLine',form,Geom.UHStatic)
        
        vdata.setNumRows(1)
        
        vertex = GeomVertexWriter(vdata,'vertex')
        
        vertex.addData3f(0,0,0)
        vertex.addData3f(0,0,10)
        
        prim = GeomLines(Geom.UHStatic)
        prim.addVertices(0,1)
        
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        
        node = GeomNode('gnode')
        node.addGeom(geom)
        
        nodePath = self.render.attachNewNode(node)
        
        
        
        
app = cApp()
app.run()

