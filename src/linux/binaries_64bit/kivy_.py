# An example of embedding CEF browser in the Kivy framework.
# The browser is embedded using off-screen rendering mode.

# Tested using Kivy 1.7.2 stable on Ubuntu 12.04 64-bit.

# In this example kivy-lang is used to declare the layout which
# contains two buttons (back, forward) and the browser view.

# The official CEF Python binaries come with tcmalloc hook
# disabled. But if you've built custom binaries and kept tcmalloc
# hook enabled, then be aware that in such case it is required
# for the cefpython module to be the very first import in
# python scripts. See Issue 73 in the CEF Python Issue Tracker
# for more details.

import ctypes, os, sys
libcef_so = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'libcef.so')
if os.path.exists(libcef_so):
    # Import local module
    ctypes.CDLL(libcef_so, ctypes.RTLD_GLOBAL)
    if 0x02070000 <= sys.hexversion < 0x03000000:
        import cefpython_py27 as cefpython
    else:
        raise Exception("Unsupported python version: %s" % sys.version)
else:
    # Import from package
    from cefpython3 import cefpython

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, GraphicException
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.base import EventLoop

####Kivy APP ####
Builder.load_string("""

<BrowserLayout>:
    orientation: 'vertical'
    BoxLayout:
        size_hint_y: None
        width: 80
        Button:
            text: "Back"
            on_press: browser.go_back()
        Button:
            text: "Forward"
            on_press: browser.go_forward()
    CefBrowser:
        id: browser

""")



class BrowserLayout(BoxLayout):

    def __init__(self, **kwargs):
        super(BrowserLayout, self).__init__(**kwargs)



class CefBrowser(Widget):

    # Keyboard mode: "global" or "local".
    # 1. Global mode forwards keys to CEF all the time.
    # 2. Local mode forwards keys to CEF only when an editable
    #    control is focused (input type=text|password or textarea).
    keyboard_mode = "global"

    '''Represent a browser widget for kivy, which can be used like a normal widget.
    '''
    def __init__(self, start_url='http://www.google.com/', **kwargs):
        super(CefBrowser, self).__init__(**kwargs)

        self.start_url = start_url

        #Workaround for flexible size:
        #start browser when the height has changed (done by layout)
        #This has to be done like this because I wasn't able to change
        #the texture size
        #until runtime without core-dump.
        self.bind(size = self.size_changed)


    starting = True
    def size_changed(self, *kwargs):
        '''When the height of the cefbrowser widget got changed, create the browser
        '''
        if self.starting:
            if self.height != 100:
                self.start_cef()
                self.starting = False
        else:
            self.texture = Texture.create(
                size=self.size, colorfmt='rgba', bufferfmt='ubyte')
            self.texture.flip_vertical()
            with self.canvas:
                Color(1, 1, 1)
                # This will cause segmentation fault:
                # | self.rect = Rectangle(size=self.size, texture=self.texture)
                # Update only the size:
                self.rect.size = self.size
            self.browser.WasResized()


    def _cef_mes(self, *kwargs):
        '''Get called every frame.
        '''
        cefpython.MessageLoopWork()


    def _update_rect(self, *kwargs):
        '''Get called whenever the texture got updated.
        => we need to reset the texture for the rectangle
        '''
        self.rect.texture = self.texture


    def start_cef(self):
        '''Starts CEF.
        '''
        # create texture & add it to canvas
        self.texture = Texture.create(
                size=self.size, colorfmt='rgba', bufferfmt='ubyte')
        self.texture.flip_vertical()
        with self.canvas:
            Color(1, 1, 1)
            self.rect = Rectangle(size=self.size, texture=self.texture)

        #configure cef
        settings = {
            "debug": True, # cefpython debug messages in console and in log_file
            "log_severity": cefpython.LOGSEVERITY_INFO,
            "log_file": "debug.log",
            # This directories must be set on Linux
            "locales_dir_path": cefpython.GetModuleDirectory()+"/locales",
            "resources_dir_path": cefpython.GetModuleDirectory(),
            "browser_subprocess_path": "%s/%s" % (
                cefpython.GetModuleDirectory(), "subprocess"),
            "windowless_rendering_enabled": True,
        }

        #start idle
        Clock.schedule_interval(self._cef_mes, 0)

        #init CEF
        cefpython.Initialize(settings)

        #WindowInfo offscreen flag
        windowInfo = cefpython.WindowInfo()
        windowInfo.SetAsOffscreen(0)

        #Create Broswer and naviagte to empty page <= OnPaint won't get called yet
        browserSettings = {}
        # The render handler callbacks are not yet set, thus an
        # error report will be thrown in the console (when release
        # DCHECKS are enabled), however don't worry, it is harmless.
        # This is happening because calling GetViewRect will return
        # false. That's why it is initially navigating to "about:blank".
        # Later, a real url will be loaded using the LoadUrl() method
        # and the GetViewRect will be called again. This time the render
        # handler callbacks will be available, it will work fine from
        # this point.
        # --
        # Do not use "about:blank" as navigateUrl - this will cause
        # the GoBack() and GoForward() methods to not work.
        self.browser = cefpython.CreateBrowserSync(windowInfo, browserSettings,
                navigateUrl=self.start_url)

        #set focus
        self.browser.SendFocusEvent(True)

        self._client_handler = ClientHandler(self)
        self.browser.SetClientHandler(self._client_handler)
        self.set_js_bindings()

        #Call WasResized() => force cef to call GetViewRect() and OnPaint afterwards
        self.browser.WasResized()

        # The browserWidget instance is required in OnLoadingStateChange().
        self.browser.SetUserData("browserWidget", self)

        if self.keyboard_mode == "global":
            self.request_keyboard()

        # Clock.schedule_once(self.change_url, 5)


    _client_handler = None
    _js_bindings = None

    def set_js_bindings(self):
        if not self._js_bindings:
            self._js_bindings = cefpython.JavascriptBindings(
                bindToFrames=True, bindToPopups=True)
            self._js_bindings.SetFunction("__kivy__request_keyboard",
                    self.request_keyboard)
            self._js_bindings.SetFunction("__kivy__release_keyboard",
                    self.release_keyboard)
        self.browser.SetJavascriptBindings(self._js_bindings)


    def change_url(self, *kwargs):
        # Doing a javascript redirect instead of Navigate()
        # solves the js bindings error. The url here need to
        # be preceded with "http://". Calling StopLoad()
        # might be a good idea before making the js navigation.

        self.browser.StopLoad()
        self.browser.GetMainFrame().ExecuteJavascript(
               "window.location='http://www.youtube.com/'")

        # Do not use Navigate() or GetMainFrame()->LoadURL(),
        # as it causes the js bindings to be removed. There is
        # a bug in CEF, that happens after a call to Navigate().
        # The OnBrowserDestroyed() callback is fired and causes
        # the js bindings to be removed. See this topic for more
        # details:
        # http://www.magpcss.org/ceforum/viewtopic.php?f=6&t=11009

        # OFF:
        # | self.browser.Navigate("http://www.youtube.com/")

    _keyboard = None

    def request_keyboard(self):
        print("request_keyboard()")
        self._keyboard = EventLoop.window.request_keyboard(
                self.release_keyboard, self)
        self._keyboard.bind(on_key_down=self.on_key_down)
        self._keyboard.bind(on_key_up=self.on_key_up)
        self.is_shift1 = False
        self.is_shift2 = False
        self.is_ctrl1 = False
        self.is_ctrl2 = False
        self.is_alt1 = False
        self.is_alt2 = False
        # Not sure if it is still required to send the focus
        # (some earlier bug), but it shouldn't hurt to call it.
        self.browser.SendFocusEvent(True)


    def release_keyboard(self):
        # When using local keyboard mode, do all the request
        # and releases of the keyboard through js bindings,
        # otherwise some focus problems arise.
        self.is_shift1 = False
        self.is_shift2 = False
        self.is_ctrl1 = False
        self.is_ctrl2 = False
        self.is_alt1 = False
        self.is_alt2 = False
        if not self._keyboard:
            return
        print("release_keyboard()")
        self._keyboard.unbind(on_key_down=self.on_key_down)
        self._keyboard.unbind(on_key_up=self.on_key_up)
        self._keyboard.release()

    # Kivy does not provide modifiers in on_key_up, but these
    # must be sent to CEF as well.
    is_shift1 = False
    is_shift2 = False
    is_ctrl1 = False
    is_ctrl2 = False
    is_alt1 = False
    is_alt2 = False


    """
    Understanding keyboard handling.
    ---------------------------------------------------------------------------

    type:

        KEYEVENT_RAWKEYDOWN = 0
        KEYEVENT_KEYDOWN = 1
        KEYEVENT_KEYUP = 2
        KEYEVENT_CHAR = 3

    From w3schools.com:

        When pressing the "a" key on the keyboard (not using caps lock),
        the result of char and key will be:

            Unicode CHARACTER code: 97     - named "charCode" in Javascript
            Unicode KEY code: 65           - named "keyCode" in Javascript

    Pressing 'a' - CEF keyboard handler:

        type=KEYEVENT_RAWKEYDOWN
        modifiers=0
        windows_key_code=65
        native_key_code=38
        character=97
        unmodified_character=97

        type=KEYEVENT_CHAR
        modifiers=0
        windows_key_code=97
        native_key_code=38
        character=97
        unmodified_character=97

        type=KEYEVENT_KEYUP
        modifiers=0
        windows_key_code=65
        native_key_code=38
        character=97
        unmodified_character=97

    Pressing Right Alt - CEF keyboard handler:

        type=KEYEVENT_RAWKEYDOWN
        modifiers=0
        windows_key_code=225
        native_key_code=108
        character=0
        unmodified_character=0

        type=KEYEVENT_KEYUP
        modifiers=0
        windows_key_code=225
        native_key_code=108
        character=0
        unmodified_character=0

    Pressing Right Alt + 'a' - CEF keyboard handler:

        type=KEYEVENT_RAWKEYDOWN
        modifiers=0
        windows_key_code=225
        native_key_code=108
        character=0
        unmodified_character=0

        type=KEYEVENT_RAWKEYDOWN
        modifiers=0
        windows_key_code=65
        native_key_code=38
        character=261
        unmodified_character=261

        type=KEYEVENT_CHAR
        modifiers=0
        windows_key_code=261
        native_key_code=38
        character=261
        unmodified_character=261

        type=KEYEVENT_KEYUP
        modifiers=0
        windows_key_code=65
        native_key_code=38
        character=261
        unmodified_character=261

        type=KEYEVENT_KEYUP
        modifiers=0
        windows_key_code=225
        native_key_code=108
        character=0
        unmodified_character=0


    Pressing 'a' - Kivy keyboard handler:

        ---- on_key_down:
        -- key=(97, 'a')
        -- modifiers=[]

        ---- on_key_up:
        -- key=(97, 'a')

    Pressing Right Alt + 'a' - Kivy keyboard handler:

        ---- on_key_down
        -- key=(313, '')
        -- modifiers=[]

        ---- on_key_down:
        -- key=(97, 'a')
        -- modifiers=[]

        ---- on_key_up:
        -- key=(97, 'a')

        ---- on_key_up
        -- key=(313, '')

    ---------------------------------------------------------------------------
    """

    def on_key_down(self, keyboard, key, text, modifiers):
        # NOTE: Right alt modifier is not sent by Kivy through modifiers param.
        print("---- on_key_down")
        print("-- keyboard="+str(keyboard))
        print("-- key="+str(key))
        print("-- modifiers="+str(modifiers))

        # CEF modifiers
        cef_modifiers = cefpython.EVENTFLAG_NONE
        if "shift" in modifiers:
            cef_modifiers |= cefpython.EVENTFLAG_SHIFT_DOWN
        if "ctrl" in modifiers:
            cef_modifiers |= cefpython.EVENTFLAG_CONTROL_DOWN
        if "alt" in modifiers:
            cef_modifiers |= cefpython.EVENTFLAG_ALT_DOWN
        if "capslock" in modifiers:
            cef_modifiers |= cefpython.EVENTFLAG_CAPS_LOCK_ON

        (keycode, charcode) = self.get_cef_key_codes(key[0])

        # On escape release the keyboard, see the injected in OnLoadStart()
        if keycode == 27:
            self.browser.GetFocusedFrame().ExecuteJavascript(
                    "__kivy__on_escape()")
            return

        # Send key event to cef: RAWKEYDOWN
        keyEvent = {
                "type": cefpython.KEYEVENT_RAWKEYDOWN,
                "native_key_code": keycode,
                "character": charcode,
                "unmodified_character": charcode,
                "modifiers": cef_modifiers
        }
        print("- SendKeyEvent: %s" % keyEvent)
        self.browser.SendKeyEvent(keyEvent)

        if keycode == 304:
            self.is_shift1 = True
        elif keycode == 303:
            self.is_shift2 = True
        elif keycode == 306:
            self.is_ctrl1 = True
        elif keycode == 305:
            self.is_ctrl2 = True
        elif keycode == 308:
            self.is_alt1 = True
        elif keycode == 313:
            self.is_alt2 = True


    def on_key_up(self, keyboard, key):
        print("---- on_key_up")
        print("-- key="+str(key))

        # CEF modifiers
        cef_modifiers = cefpython.EVENTFLAG_NONE
        if self.is_shift1 or self.is_shift2:
            cef_modifiers |= cefpython.EVENTFLAG_SHIFT_DOWN
        if self.is_ctrl1 or self.is_ctrl2:
            cef_modifiers |= cefpython.EVENTFLAG_CONTROL_DOWN
        if self.is_alt1:
            cef_modifiers |= cefpython.EVENTFLAG_ALT_DOWN

        kivycode = key[0]
        (keycode, charcode) = self.get_cef_key_codes(kivycode)

        # Send key event to cef: CHAR
        keyEvent = {
                "type": cefpython.KEYEVENT_CHAR,
                "native_key_code": keycode,
                "character": charcode,
                "unmodified_character": charcode,
                "modifiers": cef_modifiers
        }
        print("- SendKeyEvent: %s" % keyEvent)
        self.browser.SendKeyEvent(keyEvent)

        # Send key event to cef: KEYUP
        keyEvent = {
                "type": cefpython.KEYEVENT_KEYUP,
                "native_key_code": keycode,
                "character": charcode,
                "unmodified_character": charcode,
                "modifiers": cef_modifiers
        }
        print("- SendKeyEvent: %s" % keyEvent)
        self.browser.SendKeyEvent(keyEvent)

        if kivycode == 304:
            self.is_shift1 = False
        elif kivycode == 303:
            self.is_shift2 = False
        elif kivycode == 306:
            self.is_ctrl1 = False
        elif kivycode == 305:
            self.is_ctrl2 = False
        elif kivycode == 308:
            self.is_alt1 = False
        elif kivycode == 313:
            self.is_alt2 = False


    def get_cef_key_codes(self, kivycode):

        keycode = kivycode
        charcode = kivycode

        # shifts, ctrls, alts
        if kivycode in [303,304,305,306,308,313]:
            charcode = 0

        # TODO...................

        return keycode, charcode


    def go_forward(self):
        '''Going to forward in browser history
        '''
        print "go forward"
        self.browser.GoForward()


    def go_back(self):
        '''Going back in browser history
        '''
        print "go back"
        self.browser.GoBack()


    def on_touch_down(self, touch, *kwargs):
        if not self.collide_point(*touch.pos):
            return
        touch.grab(self)

        y = self.height-touch.pos[1]
        self.browser.SendMouseClickEvent(touch.x, y, cefpython.MOUSEBUTTON_LEFT,
                                         mouseUp=False, clickCount=1)


    def on_touch_move(self, touch, *kwargs):
        if touch.grab_current is not self:
            return

        y = self.height-touch.pos[1]
        self.browser.SendMouseMoveEvent(touch.x, y, mouseLeave=False)


    def on_touch_up(self, touch, *kwargs):
        if touch.grab_current is not self:
            return

        y = self.height-touch.pos[1]
        self.browser.SendMouseClickEvent(touch.x, y, cefpython.MOUSEBUTTON_LEFT,
                                         mouseUp=True, clickCount=1)
        touch.ungrab(self)


class ClientHandler:

    def __init__(self, browserWidget):
        self.browserWidget = browserWidget


    def _fix_select_boxes(self, frame):
        # This is just a temporary fix, until proper Popup widgets
        # painting is implemented (PET_POPUP in OnPaint). Currently
        # there is no way to obtain a native window handle (GtkWindow
        # pointer) in Kivy, and this may cause things like context menus,
        # select boxes and plugins not to display correctly. Although,
        # this needs to be tested. The popup widget buffers are
        # available in a separate paint buffer, so they could positioned
        # freely so that it doesn't go out of the window. So the native
        # window handle might not necessarily be required to make it work
        # in most cases (99.9%). Though, this still needs testing to confirm.
        # --
        # See this topic on the CEF Forum regarding the NULL window handle:
        # http://www.magpcss.org/ceforum/viewtopic.php?f=6&t=10851
        # --
        # See also a related topic on the Kivy-users group:
        # https://groups.google.com/d/topic/kivy-users/WdEQyHI5vTs/discussion
        # --
        # The javascript select boxes library used:
        # http://marcj.github.io/jquery-selectBox/
        # --
        # Cannot use "file://" urls to load local resources, error:
        # | Not allowed to load local resource
        print("_fix_select_boxes()")
        resources_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "kivy-select-boxes")
        if not os.path.exists(resources_dir):
            print("The kivy-select-boxes directory does not exist, " \
                    "select boxes fix won't be applied.")
            return
        js_file = os.path.join(resources_dir, "kivy-selectBox.js")
        js_content = ""
        with open(js_file, "r") as myfile:
            js_content = myfile.read()
        css_file = os.path.join(resources_dir, "kivy-selectBox.css")
        css_content = ""
        with open(css_file, "r") as myfile:
            css_content = myfile.read()
        css_content = css_content.replace("\r", "")
        css_content = css_content.replace("\n", "")
        jsCode = """
            %(js_content)s
            var __kivy_temp_head = document.getElementsByTagName('head')[0];
            var __kivy_temp_style = document.createElement('style');
            __kivy_temp_style.type = 'text/css';
            __kivy_temp_style.appendChild(document.createTextNode("%(css_content)s"));
            __kivy_temp_head.appendChild(__kivy_temp_style);
        """ % locals()
        frame.ExecuteJavascript(jsCode,
                "kivy_.py > ClientHandler > OnLoadStart > _fix_select_boxes()")


    def OnLoadStart(self, browser, frame):
        self._fix_select_boxes(frame);
        browserWidget = browser.GetUserData("browserWidget")
        if browserWidget and browserWidget.keyboard_mode == "local":
            print("OnLoadStart(): injecting focus listeners for text controls")
            # The logic is similar to the one found in kivy-berkelium:
            # https://github.com/kivy/kivy-berkelium/blob/master/berkelium/__init__.py
            jsCode = """
                var __kivy__keyboard_requested = false;
                function __kivy__keyboard_interval() {
                    var element = document.activeElement;
                    if (!element) {
                        return;
                    }
                    var tag = element.tagName;
                    var type = element.type;
                    if (tag == "INPUT" && (type == "" || type == "text"
                            || type == "password") || tag == "TEXTAREA") {
                        if (!__kivy__keyboard_requested) {
                            __kivy__request_keyboard();
                            __kivy__keyboard_requested = true;
                        }
                        return;
                    }
                    if (__kivy__keyboard_requested) {
                        __kivy__release_keyboard();
                        __kivy__keyboard_requested = false;
                    }
                }
                function __kivy__on_escape() {
                    if (document.activeElement) {
                        document.activeElement.blur();
                    }
                    if (__kivy__keyboard_requested) {
                        __kivy__release_keyboard();
                        __kivy__keyboard_requested = false;
                    }
                }
                setInterval(__kivy__keyboard_interval, 100);
            """
            frame.ExecuteJavascript(jsCode,
                    "kivy_.py > ClientHandler > OnLoadStart")


    def OnLoadEnd(self, browser, frame, httpStatusCode):
        # Browser lost its focus after the LoadURL() and the
        # OnBrowserDestroyed() callback bug. When keyboard mode
        # is local the fix is in the request_keyboard() method.
        # Call it from OnLoadEnd only when keyboard mode is global.
        browserWidget = browser.GetUserData("browserWidget")
        if browserWidget and browserWidget.keyboard_mode == "global":
            browser.SendFocusEvent(True)


    def OnLoadingStateChange(self, browser, isLoading, canGoBack,
            canGoForward):
        print("OnLoadingStateChange(): isLoading = %s" % isLoading)
        browserWidget = browser.GetUserData("browserWidget")


    def OnPaint(self, browser, paintElementType, dirtyRects, buffer, width,
            height):
        # print "OnPaint()"
        if paintElementType != cefpython.PET_VIEW:
            print "Popups aren't implemented yet"
            return

        #update buffer
        buffer = buffer.GetString(mode="bgra", origin="top-left")

        #update texture of canvas rectangle
        self.browserWidget.texture.blit_buffer(buffer, colorfmt='bgra',
                bufferfmt='ubyte')
        self.browserWidget._update_rect()

        return True


    def GetViewRect(self, browser, rect):
        width, height = self.browserWidget.texture.size
        rect.append(0)
        rect.append(0)
        rect.append(width)
        rect.append(height)
        # print("GetViewRect(): %s x %s" % (width, height))
        return True


    def OnJavascriptDialog(self, browser, originUrl, dialogType,
                   messageText, defaultPromptText, callback,
                   suppressMessage):
        suppressMessage[0] = True
        return False


    def OnBeforeUnloadJavascriptDialog(self, browser, messageText, isReload,
            callback):
        callback.Continue(allow=True, userInput="")
        return True


if __name__ == '__main__':
    class CefBrowserApp(App):
        def build(self):
            return BrowserLayout()
    CefBrowserApp().run()

    cefpython.Shutdown()