#!/usr/bin/python
# REQUIRES PYTHON 3.0!

from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from tkinter.messagebox import *
from tkinter.filedialog import askopenfilename, asksaveasfilename
from c4tm_model import CivTroopManager
from civgamedata import CivGameData
import sqlite3

def entrySet(entry, text):
    entry.delete(0, END)
    entry.insert(0, text)
    
def capitalizeFirst(s):
    return s[0].upper()+s[1:]
    
class GameDataDisplayKey:
    def __init__(self, game_data):
        self._game_data = game_data
        
    def get_unit_type_display(self, unit_type_key):
        unit_type_data = self._game_data.get_unit_type(unit_type_key)
        if unit_type_data is None: return unit_type_key
        return unit_type_data.get("display", unit_type_key) 
        
    def __call__(self, field_type, field_key):
        if field_type == "unit_type":
            return self.get_unit_type_display(field_key)
        return field_key

class ComputeStrength(object):
    def __init__(self, unit_data, game_data):
        self._unit_data = unit_data
        self._game_data = game_data
        
    def unit_type_strength(self, unit_type):
        unit_type_data = self._game_data.get_unit_type(unit_type)
        if not unit_type_data:
            raise Exception("No Such UnitType")
        return unit_type_data["strength"]
        
    def aggregate_strength(self, unit_view, year=None):
        if unit_view.unit_type == self._unit_data.COMPOSITE_UNIT_TYPE:
            aggregate_strength = 0
            for sub_unit in unit_view.subordinate_units:
                sub_unit_view = self.manager.get_unit_view(sub_unit, self._game_data, year, GameDataDisplayKey(self._game_data))
                aggregate_strength += self.aggregate_strength(sub_unit_view, year)
        else:
            aggregate_strength = self.unit_type_strength(unit_view.unit_type)
        return aggregate_strength
        
    def average_strength(self, unit_view, year=None):
        if unit_view.unit_type == self._unit_data.COMPOSITE_UNIT_TYPE:
            sub_unit_count = len(unit_view.subordinate_units)
            if sub_unit_count == 0: return 0
            
            aggregate_strength = self.aggregate_strength(unitView, year)
            average_strength = aggregate_strength / float(sub_unit_count)
        else:
            average_strength = self.unit_type_strength(unit_view.unit_type)
        return average_strength
        
    def composite(self, unit_view, year=None):
        if unit_view.unit_type == self._unit_data.COMPOSITE_UNIT_TYPE:
            return "%d (%0.2f/%d)" % (self.aggregate_strength(unit_view, year), 
                                    self.average_strength(unit_view, year), 
                                    len(unit_view.subordinateUnits))
        else:
            return "%d%s" % (self.aggregate_strength(unit_view, year), "+"*len(unit_view.promotions))

def gui_entry_to_int(field_name, entry_data, min_val=None, max_val=None):
    try:
        i_val = int(entry_data)
    except:
        showinfo('Error', "{} value [{}] is invalid.".format(field_name, entry_data))
        return None 
    if min_val is not None and i_val < min_val:
        showinfo('Error', "{} value {} too small. Minimum value is {}".format(field_name, i_val, min_val))
        return None
    if max_val is not None and i_val > max_val:
        showinfo('Error', "{} value {} too big. Maximum value is {}".format(field_name, i_val, max_val))       
        return None
    return i_val

class SelectionBox(object):
    def __init__(self, parent, label, items, selection_change_cb=None, display_key=None):
        self._items = items
        self._display_items = items
        if display_key:
            self._display_items = [display_key(i) for i in items]
        self._selection_change_cb = selection_change_cb
        self.frame = Frame(parent)
        labelFrame = Frame(self.frame, bd=2)
        Label(labelFrame, text=label).pack(side=LEFT)
        self._selectedVar = StringVar()
        Label(labelFrame, textvariable=self._selectedVar).pack(side=RIGHT)
        labelFrame.pack()
        
        selectFrame = Frame(self.frame, bd=2, relief=SUNKEN)
        
        scrollbar = Scrollbar(selectFrame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self._selectBox = Listbox(selectFrame, yscrollcommand=scrollbar.set, selectmode=BROWSE)
        self._selectBox.insert(0, *(self._display_items))
        self._selectBox.bind("<Key>", self._jumpToSelect)
        self._selectBox.bind("<<ListboxSelect>>", self._setSelectedLabel)
        self._selectBox.activate(0)
        self._setActiveSelected()
        self._selectBox.pack(fill=BOTH, expand=1)
        selectFrame.pack(fill=BOTH, expand=1)
        
        scrollbar.config(command=self._selectBox.yview)
        
    def selected(self):
        return self._selectedVar.get()
        
    def selected_index(self):
        return self._selectBox.curselection()[0]
        
    def selected_full_item(self):
        index = self._selectBox.curselection()[0]
        return self._items[index]
        
    def set_selection_callback(self, cb):
        self._selection_change_cb = cb
        self._setSelectedLabel(None)
    
    def _setSelectedLabel(self, event):
        curselection = self._selectBox.curselection()
        if len(curselection) != 1:
            # this shouldn't happen. Maybe an exception? For now, just ignore.
            return
        selectedText = self._selectBox.get(curselection[0])
        self._selectedVar.set(selectedText)
        if self._selection_change_cb:
            self._selection_change_cb(selectedText)
        
    def _setActiveSelected(self):
        curselection = self._selectBox.curselection()
        if curselection:
            self._selectBox.select_clear(0, "end")
        self._selectBox.select_set(ACTIVE)
        self._setSelectedLabel(None)
        
    def _jumpToSelect(self, event):
        letterPressed = event.char
        if "a" <= letterPressed <= "z":
            letterIndices = []
            for i in range(len(self._display_items)):
                item = self._display_items[i]
                if item[0].lower() == letterPressed: 
                    letterIndices.append(i)
            curActive = self._selectBox.index(ACTIVE)
            if curActive not in letterIndices:
                toActivate = letterIndices[0]
            else:
                toActivate = letterIndices[(letterIndices.index(curActive)+1)%len(letterIndices)]
                
            self._selectBox.activate(toActivate)
            self._selectBox.see(toActivate)
            self._setActiveSelected()
            self._selectBox.event_generate("<<ListboxSelect>>")
            return
        else:
            # We've pressed some other key. If it's changed activate, follow with selection
            self.frame.after(100, self._setActiveSelected)
            
class OkCancelContinueDialog(object):
    def __init__(self, parent, onOk=None, onCancel=None, onContinue=None):
        self.onOk = onOk
        self.onCancel = onCancel
        self.onContinue = onContinue
        self.top = Toplevel(parent)
        
    def _insertButtonFrame(self, parent=None, rename_save=None):
        if parent == None:
            parent = self.top
        buttonFrame = Frame(parent)
        b = Button(buttonFrame, text=rename_save and rename_save or "Save", command=self.ok)
        b.pack(pady=5, side=LEFT)
        
        if self.onContinue:
            b = Button(buttonFrame, text="Save and Continue", command=self.next)
            b.pack(pady=5)
            
        b = Button(buttonFrame, text="Cancel", command=self.cancel)
        b.pack(pady=5, side=RIGHT)
        buttonFrame.pack(padx=10, fill=X, expand=1)
        
    def _ok(self):
        showinfo("Error", "Not Fully Implemented")
        return "close", None

    def ok(self):
        action, okArgs = self._ok()
        if action == "ok" and self.onOk:
            self.onOk(*okArgs)
        if action in ["close", "ok"]:
            self.top.destroy()
        
    def next(self):
        action, okArgs = self._ok()
        if action in ["close", "ok"]:
            self.top.destroy()
        if action == "ok":
            self.onOk(*okArgs)
            self.onContinue(*okArgs)
        
    def cancel(self):
        if self.onCancel:
            try:
                self.onCancel()
            except:
                pass
        self.top.destroy()
        
class CreateUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(CreateUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        
        composite_label = "--CompositeUnit--"
        
        unit_type_keys = game_data.get_unit_types()
        unit_type_keys.append(composite_label)
        display_key = GameDataDisplayKey(game_data)
        self.unitTypes = unit_type_keys
        
        unit_type_keys.sort(key=display_key.get_unit_type_display)
        self.manager = manager

        top = self.top
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)

        Label(top, text="New Unit Name:").pack()

        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)
        
        """self.unitTypeVar = StringVar(top)
        self.unitTypeVar.set(unitTypes[0]) # initial value

        self.unitTypeSelect = OptionMenu(top, self.unitTypeVar, *unitTypes)
        self.unitTypeSelect.bind_all("<Key>", self._jumpUnitTypeSelect)
        self.unitTypeSelect.pack()"""
        
        self.unitTypeSelect = SelectionBox(top, "Unit Type:", unit_type_keys, display_key=display_key.get_unit_type_display)
        self.unitTypeSelect.frame.pack(fill=BOTH, expand=1)
        
        Label(top, text="Starting Location:").pack()
        self.locationEntry = Entry(top)
        self.locationEntry.pack(padx=5)

        self._insertButtonFrame()
    

    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        if not self.nameEntry.get():
            showinfo('Error', "No unit name specified.")
            return "retry", None
        if not self.locationEntry.get():
            showinfo("Error", "No unit starting location specified")
            return "retry", None
        
        try:
            with self.manager:
                unitType = self.unitTypeSelect.selected_full_item()
                if unitType == "--CompositeUnit--":
                    unitType = self.manager.COMPOSITE_UNIT_TYPE
                unitId = self.manager.create_unit(year, self.nameEntry.get(), unitType, self.locationEntry.get())
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (unitId, year)
            

        
class PromoteUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(PromoteUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Promote '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)
        
        Label(top, text="Current Promotions.").pack()
        
        displayFrame = Frame(top, bd=2, relief=SUNKEN)
        
        scrollbar = Scrollbar(displayFrame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.promotionDisplay =  Listbox(displayFrame, yscrollcommand=scrollbar.set)
        self.promotionDisplay.insert(0, *self.unitView.display.promotions)
        self.promotionDisplay.pack(fill=BOTH, expand=1)
        displayFrame.pack(fill=BOTH, expand=1)
        
        availablePromotions = []
        for promotion in game_data.get_promotions():
            if promotion not in self.unitView.display.promotions:
                availablePromotions.append(promotion)
        
        Label(top, text="Promotions (click on all that apply).").pack()
        
        selectFrame = Frame(top, bd=2, relief=SUNKEN)
        
        scrollbar = Scrollbar(selectFrame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.promotionSelect =  Listbox(selectFrame, yscrollcommand=scrollbar.set, selectmode=MULTIPLE)
        self.promotionSelect.insert(0, *availablePromotions)
        self.promotionSelect.pack(fill=BOTH, expand=1)
        selectFrame.pack(fill=BOTH, expand=1)

        self._insertButtonFrame()
        
    def _ok(self):
        curselection = self.promotionSelect.curselection()
        if not curselection:
            showinfo("Error", "No promotions selected")
            return "retry", None
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        try:
            with self.manager:
                for selectionIndex in curselection:
                    promotion = self.promotionSelect.get(selectionIndex)
                    self.manager.promote_unit(self.unit, year, promotion)
        except Exception as e:
            showinfo("Database Error", str(e))
            return "retry", None
        return "ok", (self.unit, year)
        
class UpgradeUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(UpgradeUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Upgrade '%s'." % self.unitView.display.name).pack()
        Label(top, text="Current type: {}".format(self.unitView.display.unit_type)).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)
        
        unit_type_keys = game_data.get_unit_types()
        display_key = GameDataDisplayKey(game_data)
        
        self.unitTypeSelect = SelectionBox(top, "Upgrade Unit Type:", unit_type_keys, display_key=display_key.get_unit_type_display)
        self.unitTypeSelect.frame.pack()

        self._insertButtonFrame()
        
    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
            
        unitType = self.unitTypeSelect.selected_full_item()
        if not unitType:
            showinfo("Error", "No Upgrade Type Selected")
            return "retry", None
        if unitType == self.unitView.unit_type:
            showinfo("Error", "Cannot upgrade to the same unit type")
            return "retry", None
        
        try:
            with self.manager:
                self.manager.upgrade_unit(self.unit, year, unitType)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, year)
        
class MoveUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(MoveUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        display_key = GameDataDisplayKey(game_data)
        self.unitView = manager.get_unit_view(unit, yearHint, display_key)
        self.manager = manager
        subUnitViews = list(map(lambda subId: self.manager.get_unit_view(subId, yearHint, display_key), self.unitView.subordinate_units))
        queuePointer = 0
        while len(subUnitViews) > queuePointer:
            nextUnitView = subUnitViews[queuePointer]
            subUnitViews += nextunitView.subordinate_units
            queuePointer += 1
        subUnits = []
        self.subUnitNames = {}
        for subUnitView in subUnitViews:
            compositeUnit = self.manager.get_unit_view(subunitView.composite_unit_id, yearHint, data_key).display.name
            displayName = "%d. %s: %s (%s)" % (subUnitView.display.id, subUnitView.display.name, compositeUnit, subUnitView.display.location)
            subUnits.append(displayName)
            self.subUnitNames[displayName] = subUnitView.id

        top = self.top
        
        if self.unitView.unit_type == manager.COMPOSITE_UNIT_TYPE:
            Label(top, text="Set deployment location of composite unit '%s'." % self.unitView.display.name).pack()
        else:
            Label(top, text="Set physical location of civ unit '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)
        
        Label(top, text="Current location is '%s'. Enter new location:" % self.unitView.display.location).pack()
        self.locationEntry = Entry(top)
        self.locationEntry.pack(padx=5)
        
        if subUnits:
            Label(top, text="Select subunits deploying with '%s' to new location." % self.unitView.display.name).pack()
        
            displayFrame = Frame(top, bd=2, relief=SUNKEN)
            
            scrollbar = Scrollbar(displayFrame)
            scrollbar.pack(side=RIGHT, fill=Y)
            
            self.subunitDisplay =  Listbox(displayFrame, yscrollcommand=scrollbar.set, selectmode=MULTIPLE)
            self.subunitDisplay.insert(0, *subUnits)
            self.subunitDisplay.pack()
            displayFrame.pack()


        self._insertButtonFrame()
        
    def _ok(self):
        newLocation = self.locationEntry.get()
        if not newLocation:
            showinfo('Error', 'Cannot leave location empty.')
            return "retry", None
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        try:
            with self.manager:
                self.manager.move_unit(self.unit, year, newLocation)
                if self.subUnitNames:
                    for selectionIndex in self.subunitDisplay.curselection():
                        displayName = self.subunitDisplay.get(selectionIndex)
                        subUnit = self.subUnitNames[displayName]
                        self.manager.move_unit(subUnit, year, newLocation)
        except Exception as e:
            showinfo("Database Error", str(e))
            return "retry", None
        return "ok", (self.unit, year)
        
        
class TransferHQDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(TransferHQDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Move Headquarters for '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)
        
        Label(top, text="Current HQ is '%s'. Enter new HQ:" % self.unitView.display.HQ).pack()
        self.hqEntry = Entry(top)
        self.hqEntry.pack(padx=5)
        
        subUnits = []
        self.subUnitNames = {}
        for subUnit in self.unitView.subordinate_units:
            subUnitView = manager.get_unit_view(subUnit, yearHint, GameDataDisplayKey(game_data))
            if subunitView.unit_type != manager.COMPOSITE_UNIT_TYPE:
                displayName = "%d. %s (%s)" % (subUnitView.display.id, subUnitView.display.name, subUnitView.display.HQ)
                subUnits.append(displayName)
                self.subUnitNames[displayName] = subUnitView.id
        
        if subUnits:
            Label(top, text="Select immediate subordinate civ units changing HQ with '%s'." % self.unitView.display.name).pack()
        
            displayFrame = Frame(top, bd=2, relief=SUNKEN)
            
            scrollbar = Scrollbar(displayFrame)
            scrollbar.pack(side=RIGHT, fill=Y)
            
            self.subunitDisplay =  Listbox(displayFrame, yscrollcommand=scrollbar.set, selectmode=MULTIPLE)
            self.subunitDisplay.insert(0, *subUnits)
            self.subunitDisplay.pack()
            displayFrame.pack()

        self._insertButtonFrame()
        
    def _ok(self):
        newHQ = self.hqEntry.get()
        if not newHQ:
            # no changes. End
            showinfo('Error', 'HQ Must be specified.')
            return "retry", None
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        try:
            with self.manager:
                self.manager.transfer_unit_hq(self.unit, year, newHQ)
                if self.subUnitNames:
                    for selectionIndex in self.subunitDisplay.curselection():
                        displayName = self.subunitDisplay.get(selectionIndex)
                        subUnit = self.subUnitNames[displayName]
                        self.manager.transfer_unit_hq(subUnit, year, newHQ)
        except Exception as e:
            showinfo("Database Error", str(e))
            return "retry", None
        return "ok", (self.unit, year)
        
class RenameUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(RenameUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Rename '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        self.yearEntry.pack(padx=5)
        
        Label(top, text="Enter new name:" ).pack()
        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)


        self._insertButtonFrame()
        
    def _ok(self):
        newName = self.nameEntry.get()
        if not newName:
            showinfo('Error', 'Cannot leave name empty.')
            return "retry", None
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None

        try:
            with self.manager:
                self.manager.rename_unit(self.unit, year, newName)
        except Exception as e:
            showinfo("Database Error", str(e))
            return "retry", None
        return "ok", (self.unit, year)
        
class AssignUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, compositeUnits, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(AssignUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.compositeUnitViews = map(lambda cId: manager.get_unit_view(cId, yearHint), compositeUnits)
        self.manager = manager

        top = self.top
        
        Label(top, text="Assign '%s' to Metaunit." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        else:
            yearHint = "most recent"
        self.yearEntry.pack(padx=5)
        
        compositeUnitNames = []
        self.compositeUnitLookup = {}
        for compositeUnitView in self.compositeUnitViews:
            displayName = "%d. %s" % (compositeUnitView.display.id, compositeUnitView.display.name)
            self.compositeUnitLookup[displayName] = compositeUnitView.id
            compositeUnitNames.append(displayName)
        
        self.compositeUnitSelect = SelectionBox(top, "Composite Units as of %s:" % yearHint, compositeUnitNames)
        self.compositeUnitSelect.frame.pack()
        
        self.transferHqVar = IntVar()

        c = Checkbutton(top, text="Transfer HQ to Composite?", variable=self.transferHqVar)
        c.pack()
        
        self._insertButtonFrame()
        
    

    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        try:
            with self.manager:
                compositeUnitDisplayName = self.compositeUnitSelect.selected()
                compositeUnitId = self.compositeUnitLookup[compositeUnitDisplayName]
                self.manager.assign_unit_to_composite(self.unit, year, compositeUnitId)
                if self.transferHqVar.get() == 1:
                    compositeUnitView = self.manager.get_unit_view(compositeUnitId, year)
                    self.manager.transfer_unit_hq(self.unit, year, compositeUnitView.display.HQ)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, year)

class DeleteUnitEventDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(DeleteUnitEventDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Delete event from '%s' (%d) history. CANNOT BE UNDONE!" % (self.unitView.display.name, unit)).pack()
        
        self.yearHint = yearHint
        
        unitEvents = []
        self.unitEventMapping = {}
        for eventData in self.unitView.display.history:
            eventId, eventYear, eventNote = eventData
            displayName = "%d. %s (event id %d)" % (eventYear, eventNote, eventId)
            unitEvents.append(displayName)
            self.unitEventMapping[displayName] = eventId
        unitEvents.reverse()
        self.unitEventSelect = SelectionBox(top, "Unit Events as of year %d" % yearHint, unitEvents)
        self.unitEventSelect.frame.pack()
        
        self._insertButtonFrame(rename_save="Delete")

    def _ok(self):
        selectedEvent = self.unitEventSelect.selected()
        if not selectedEvent:
            showinfo('Error', 'No Event Selected')
            return "retry", None
        selectedEventId = self.unitEventMapping[selectedEvent]
        try:
            with self.manager:
                self.manager.delete_event(selectedEventId)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, self.yearHint)
        
class DestroyUnitDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(DestroyUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Destroy unit '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        else:
            yearHint = "most recent"
        self.yearEntry.pack(padx=5)
        
        unit_types = game_data.get_unit_types()
        display_key = GameDataDisplayKey(game_data)
        self.unitDestroyerSelect = SelectionBox(top, "Select unit type that destroyed '%s' (optional)" % self.unitView.display.name, unit_types, display_key = display_key.get_unit_type_display)
        self.unitDestroyerSelect.frame.pack()
        
        Label(top, text="Unit owner (leave blank if no selected unit):").pack()
        self.ownerEntry = Entry(top)
        self.ownerEntry.pack(padx=5)
        
        Label(top, text="Unit name (optional, leave blank if no selected unit):").pack()
        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)
        
        Label(top, text="Historic Details (optional):").pack()
        
        self.detailsEntry = Entry(top)
        self.detailsEntry.pack(padx=5)
        
        self._insertButtonFrame()

    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        details = self.detailsEntry.get()
        destroyerUnitType = self.unitDestroyerSelect.selected()
        if not destroyerUnitType:
            destroyerUnitType = None
        else:
            destroyerOwner = self.ownerEntry.get()
            if not destroyerOwner:
                showinfo('Error', "The selected unit's owner cannot be blank")
                return "retry", None
            destroyerOwner = capitalizeFirst(destroyerOwner)
            destroyerName = self.nameEntry.get()
            if not destroyerName:
                destroyerName = None
        try:
            with self.manager:
                self.manager.destroy_unit(self.unit, year, destroyerUnitType, destroyerOwner, destroyerName)
                if details:
                    self.manager.unit_history(self.unit, year, details)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, year)
        
class RecordUnitHistoryDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(RecordUnitHistoryDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="New history event for unit '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        else:
            yearHint = "most recent"
        self.yearEntry.pack(padx=5)
        
        Label(top, text="Details:").pack()
        
        self.detailsEntry = Entry(top)
        self.detailsEntry.pack(padx=5)
        
        self._insertButtonFrame()

    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        details = self.detailsEntry.get()
        if not details:
            showinfo('Error', 'No Details to record')
            return "retry", None

        try:
            with self.manager:
                self.manager.unit_history(self.unit, year, details)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, year)
        
class RecordVictoryDialog(OkCancelContinueDialog):
    def __init__(self, parent, unit, manager, game_data, yearHint=None, onOk=None, onCancel=None, onContinue=None):
        super(RecordVictoryDialog, self).__init__(parent, onOk, onCancel, onContinue)
        self.unit = unit
        self.display_key = GameDataDisplayKey(game_data)
        self.unitView = manager.get_unit_view(unit, yearHint, GameDataDisplayKey(game_data))
        self.manager = manager

        top = self.top
        
        Label(top, text="Record victory for unit '%s'." % self.unitView.display.name).pack()
        
        Label(top, text="Year (negative for BC):").pack()
        self.yearEntry = Entry(top)
        if yearHint != None:
            entrySet(self.yearEntry, yearHint)
        else:
            yearHint = "most recent"
        self.yearEntry.pack(padx=5)
        
        unit_types = game_data.get_unit_types()
        self.unitDestroyedSelect = SelectionBox(top, "Select unit type that '%s' destroyed" % self.unitView.display.name, unit_types, display_key=self.display_key.get_unit_type_display)
        self.unitDestroyedSelect.frame.pack()
        
        Label(top, text="Unit owner:").pack()
        self.ownerEntry = Entry(top)
        self.ownerEntry.pack(padx=5)
        
        Label(top, text="Unit name (optional):").pack()
        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)
        
        Label(top, text="Details (optional):").pack()
        
        self.detailsEntry = Entry(top)
        self.detailsEntry.pack(padx=5)
        
        self._insertButtonFrame()

    def _ok(self):
        try:
            year = int(self.yearEntry.get())
        except:
            showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
            return "retry", None
        details = self.detailsEntry.get()
        destroyedUnitType = self.unitDestroyedSelect.selected()
        if not destroyedUnitType:
            showinfo('Error', "No destroyed unit type selected.")
            return "retry", None
        destroyedUnitOwner = self.ownerEntry.get()
        if not destroyedUnitOwner:
            showinfo('Error', "No destroyed unit owner entered")
            return "retry", None
        destroyedUnitOwner = capitalizeFirst(destroyedUnitOwner)
        destroyedUnitName = self.nameEntry.get()
        if not destroyedUnitName:
            destroyedUnitName = None

        try:
            with self.manager:
                self.manager.unit_victory(self.unit, year, destroyedUnitType, destroyedUnitOwner, destroyedUnitName)
                if details:
                    self.manager.unit_history(self.unit, year, details)
        except Exception as e:
            showinfo('Database Error', str(e))
            return "close", None
        return "ok", (self.unit, year)
        
class CreateOrEditUnitTypeDialog():
    def __init__(self, parent, game_data, edit=False):
        self.game_data = game_data
        self.display_key = GameDataDisplayKey(game_data)
        self.edit = edit
        

        top = self.top = Toplevel(parent)
        if self.edit:
            unit_types = self.game_data.get_unit_types()
            unit_types.sort()
            self.unitTypeSelect = SelectionBox(top, "Edit Unit Type:", 
                unit_types
                )
            self.unitTypeSelect.frame.pack(fill=BOTH, expand=1)
        else:
            Label(top, text="Unit Type Unique Key:").pack()
            self.dbkeyEntry = Entry(top)
            self.dbkeyEntry.pack(padx=5)
        
        Label(top, text="Unit Type Name:").pack()
        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)
        
        Label(top, text="Unit Class:").pack()
        self.unitClassEntry = Entry(top)
        self.unitClassEntry.pack()
        
        Label(top, text="Strength:").pack()
        self.strengthEntry = Entry(top)
        self.strengthEntry.pack(padx=5)
        
        Label(top, text="Movement or Range:").pack()
        self.moveEntry = Entry(top)
        self.moveEntry.pack(padx=5)
        
        Label(top, text="Cost:").pack()
        self.costEntry = Entry(top)
        self.costEntry.pack(padx=5)
        
        
        buttonFrame = Frame(self.top)
        if self.edit:
            okText = "Save"
        else:
            okText = "Create"
        b = Button(buttonFrame, text=okText, command=self.ok)
        b.pack(pady=5, side="left")
        b = Button(buttonFrame, text="Cancel", command=self.top.destroy)
        b.pack(pady=5, side="right")
        #self._insertButtonFrame()
        buttonFrame.pack(padx=10, fill=X, expand=1)
        
        if self.edit:
            self.unitTypeSelect.set_selection_callback(self._populate_fields)
        
    def _populate_fields(self, unit_type_key):
        unit_type_data = self.game_data.get_unit_type(unit_type_key)
        if unit_type_data is None:
            unit_type_data = {}
        entrySet(self.nameEntry, unit_type_data.get("display","????"))
        entrySet(self.unitClassEntry, unit_type_data.get("class", "????"))
        entrySet(self.strengthEntry, unit_type_data.get("strength", "????"))
        entrySet(self.moveEntry, unit_type_data.get("move", "????"))
        entrySet(self.costEntry, unit_type_data.get("cost", "????"))
        
    def _ok(self):
        strength = gui_entry_to_int("strength", self.strengthEntry.get(), min_val=0)
        move = gui_entry_to_int("movement", self.moveEntry.get(), min_val=0)
        cost = gui_entry_to_int("cost", self.costEntry.get(), min_val=0)
        
        if self.edit:
            dbkey = self.unitTypeSelect.selected()
        elif not self.dbkeyEntry.get():
            showinfo('Error', "No unit unique key specified.")
            return
        else:
            dbkey = self.dbkeyEntry.get()
            
        if not self.nameEntry.get():
            showinfo('Error', "No unit name specified.")
            return
            
        if not self.unitClassEntry.get():
            showinfo('Error', "No unit class specified.")
        
        try:
            self.game_data.set_unit_type(
                dbkey, 
                self.nameEntry.get(), 
                self.unitClassEntry.get(),
                strength, 
                move, 
                cost, 
                overwrite=self.edit)
        except Exception as e:
            showinfo('Error', str(e))
            return
            
    def ok(self):
        self._ok()
        self.top.destroy()
        
class CreateOrEditPromotionTypeDialog(object):
    def __init__(self, parent, game_data, edit=False):
        self.game_data = game_data
        self.edit = edit

        top = self.top = Toplevel(parent)
        
        if self.edit:
            promotions = self.game_data.get_promotions()
            promotions.sort()
            self.promotionSelect = SelectionBox(top, "Edit Promotion:", promotions)
            self.promotionSelect.frame.pack(fill=BOTH, expand=1)
            
            Label(top, text="Rename Promotion:").pack()
        else:
            Label(top, text="Promotion Type Name:").pack()
        self.nameEntry = Entry(top)
        self.nameEntry.pack(padx=5)
        
        buttonFrame = Frame(self.top)
        if self.edit:
            okText = "Rename"
        else:
            okText = "Create"
        b = Button(buttonFrame, text=okText, command=self.ok)
        b.pack(pady=5, side="left")
        if self.edit:
            b = Button(buttonFrame, text="Delete", command=self.delete)
            b.pack(pady=5)
        b = Button(buttonFrame, text="Cancel", command=self.top.destroy)
        b.pack(pady=5, side="right")
        #self._insertButtonFrame()
        buttonFrame.pack(padx=10, fill=X, expand=1)
        
    def _ok(self):
            
        if not self.nameEntry.get():
            showinfo('Error', "No promotion name entered.")
            return "retry"
        
        try:
            if self.edit:
                self.game_data.del_promotion(self.promotionSelect.selected())
            self.game_data.add_promotion(self.nameEntry.get())
        except Exception as e:
            showinfo('Error', str(e))
            return "retry"
        return "ok"
        
    def _delete(self):
            
        if self.nameEntry.get():
            showinfo('Error', "To delete, rename field must be empty.")
            return "retry"
        
        try:
                self.game_data.del_promotion(self.promotionSelect.selected())
        except Exception as e:
            showinfo('Error', str(e))
            return "retry"
        return "ok"
            
    def ok(self):
        res = self._ok()
        if res == "ok":
            self.top.destroy()
            
    def delete(self):
        res = self._delete()
        if res == "ok":
            self.top.destroy()

class Civ4TroopManager_tkinterView(object):
    def __init__(self, databaseName=None, game_data_file=None):
        self._troopManagerModel = None
        self._strengthModel = None
        self.initView()
        self._game_data = CivGameData(game_data_file)
        self._display_key = GameDataDisplayKey(self._game_data)
        if databaseName:
            self._openDatabase(databaseName)
        
    def initView(self):
        self._root = Tk()

        """ Image exampletext1 = Text(root, height=20, width=30)
        photo=PhotoImage(file='./William_Shakespeare.gif')
        text1.insert(END,'\n')
        text1.image_create(END, image=photo)

        text1.pack(side=LEFT)"""
        
        yearFrame = Frame(self._root)
        self._yearEntry = Entry(yearFrame)
        self._yearEntry.pack(pady=5, side=LEFT)
        
        yearButtonFrame = Frame(yearFrame)
        
        b1 = Button(yearButtonFrame, text="Latest", command=self.refresh)
        b1.pack(pady=5, side=RIGHT)
        b2 = Button(yearButtonFrame, text="Refresh", command=self._fillTree)
        b2.pack(pady=5, side=LEFT)
        
        yearButtonFrame.pack()
        yearFrame.pack()
        
        optionsFrame = Frame(self._root)
        
        self._displayFlatVar = IntVar()
        c1 = Checkbutton(optionsFrame, text="Display Flat?", variable=self._displayFlatVar)
        c1.pack(padx=5, side=LEFT)
        
        self._displayDeadVar = IntVar()
        c2 = Checkbutton(optionsFrame, text="Display Dead Units?", variable=self._displayDeadVar)
        c2.pack(padx=5, side=RIGHT)
        optionsFrame.pack()
        
        self._armyList = ttk.Treeview(self._root)

        columnDefinitions = [
            ("#0","ID",50),
            ("name","Name",100),
            ("type","Type",100),
            ("hq","HQ",100),
            ("location","Location",100),
            ("strength","Strength",100),
        ]
        # add in additional columns
        self._armyList["columns"]=list(map(lambda colDef: colDef[0], columnDefinitions[1:]))
        
        # set the spacing and header of each column
        for colDef in columnDefinitions:
            self._armyList.column(colDef[0], width=colDef[2])
            self._armyList.heading(colDef[0], text=colDef[1])

        self._armyList.pack(fill=BOTH, expand=1)

        """id2 = tree.insert("", 1, "dir2", text="Dir 2")
        tree.insert(id2, "end", "dir 2", text="sub dir 2", values=("2A","2B"))

        ##alternatively:
        tree.insert("", 3, "dir3", text="Dir 3")
        tree.insert("dir3", 3, text=" sub dir 3",values=("3A"," 3B"))"""
        """self._armySelect = ListBox(self._root)
        self._armySelectScroll = Scrollbar(self._root, command=self._armySelect.yview)
        self._armySelect.configure(yscrollcommand=self._armySelectScroll.set)"""
        
        """ Army Columns
        Name    Type    HQ    Location    Strength
        """

        """ Scroll Text Example
        text2 = Text(root, height=20, width=50)
        scroll = Scrollbar(root, command=text2.yview)
        text2.configure(yscrollcommand=scroll.set)
        text2.tag_configure('bold_italics', font=('Arial', 12, 'bold', 'italic'))
        text2.tag_configure('big', font=('Verdana', 20, 'bold'))
        text2.tag_configure('color', foreground='#476042', 
                                font=('Tempus Sans ITC', 12, 'bold'))
        text2.tag_bind('follow', '<1>', lambda e, t=text2: t.insert(END, "Not now, maybe later!"))
        text2.insert(END,'\nWilliam Shakespeare\n', 'big')
        quote = ""
        To be, or not to be that is the question:
        Whether 'tis Nobler in the mind to suffer
        The Slings and Arrows of outrageous Fortune,
        Or to take Arms against a Sea of troubles,
        ""
        text2.insert(END, quote, 'color')
        text2.insert(END, 'follow-up\n', 'follow')
        text2.pack(side=LEFT)
        scroll.pack(side=RIGHT, fill=Y)"""
        
        menubar = Menu(self._root)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="New", command=self._newGame)
        filemenu.add_command(label="Open", command=self._openGame)
        filemenu.add_command(label="Save Civ Game Data", command=self._saveUnitDb)
        #filemenu.add_command(label="Close", command=self._close)
        filemenu.add_command(label="Exit", command=self._exit)
        menubar.add_cascade(label="File", menu=filemenu)
        
        unitmenu = Menu(menubar, tearoff=0)
        unitmenu.add_command(label="Create", command=self._createUnit)
        unitmenu.add_command(label="View Details", command=self._viewDetails)
        unitmenu.add_command(label="Rename", command=self._renameUnit)
        unitmenu.add_command(label="Assign Metaunit", command=self._assignMetaUnit)
        unitmenu.add_command(label="Move", command=self._moveUnit)
        unitmenu.add_command(label="Transfer HQ", command=self._transferUnitHq)
        unitmenu.add_command(label="Upgrade", command=self._upgradeUnit)
        unitmenu.add_command(label="Promote", command=self._promoteUnit)
        unitmenu.add_command(label="Destroy", command=self._destroyUnit)
        unitmenu.add_command(label="Record victory", command=self._recordUnitVictory)
        unitmenu.add_command(label="Record history", command=self._recordUnitHistory)
        unitmenu.add_command(label="Delete Event", command=self._deleteUnitEvent)
        menubar.add_cascade(label="Unit Actions", menu=unitmenu)
        
        unittypemenu = Menu(menubar, tearoff=0)
        unittypemenu.add_command(label="Create Unit Type", command=self._createUnitType)
        unittypemenu.add_command(label="Edit Unit Type", command=self._editUnitType)
        unittypemenu.add_command(label="Create Promotion Type", command=self._createPromotionType)
        unittypemenu.add_command(label="Edit Promotion Type", command=self._editPromotionType)
        menubar.add_cascade(label="Definitions", menu=unittypemenu)

        self._root.config(menu=menubar)
    
    def mainLoop(self):
        self._root.mainloop()
        
    def _openDatabase(self, filename):
        gameDb = sqlite3.connect(filename)
        self._troopManagerModel = CivTroopManager(gameDb)
        self._strengthModel = ComputeStrength(self._troopManagerModel, self._game_data)
        self._fillTree()
        
    def _getSelectedUnit(self):
        curTreeSelections = self._armyList.selection()
        if len(curTreeSelections) == 1:
            return self._armyList.item(curTreeSelections[0])["text"]
        else:
            return None
            
    def _getYear(self):
        minYear, maxYear = self._troopManagerModel.get_min_max_years()
        if minYear == None:
            minYear, maxYear = -4000, -4000
        if self._yearEntry.get() == "":
            year = maxYear
            entrySet(self._yearEntry, maxYear)
        else:
            try:
                year = int(self._yearEntry.get())
                if year < minYear:
                    year = minYear
                    entrySet(self._yearEntry, year)
            except:
                year = maxYear
                entrySet(self._yearEntry, maxYear)
        return year
        
    def refresh(self):
        entrySet(self._yearEntry,"")
        self._fillTree()
        
    def _insertToTree(self, unitView, year):
        return self._armyList.insert("" , 0, text=unitView.display.id, 
                                    values=(
                                        unitView.display.name, 
                                        unitView.display.unit_type, 
                                        unitView.display.HQ, 
                                        unitView.display.location,
                                        self._strengthModel.composite(unitView, year)))
        
    def _fillTree(self, selectedUnit=None, selectedYear=None):
        if selectedYear != None:
            year = selectedYear
            entrySet(self._yearEntry, year)
        else:
            year = self._getYear()
        if self._displayFlatVar.get() == 0:
            self._fillTreeHierarchy(selectedUnit, year)
        else:
            self._fillTreeFlat(selectedUnit, year)
        
    def _fillTreeHierarchy(self, selectedUnit=None, selectedYear=None):
        self._armyList.delete(*self._armyList.get_children())
        
        unitIdList = self._troopManagerModel.get_unit_list(selectedYear)
        unitIdMap = {}
        for unitId in unitIdList:
            unitView = self._troopManagerModel.get_unit_view(unitId, selectedYear, self._display_key)
            if self._displayDeadVar.get() == 0 and unitView.is_dead: continue
            if unitView.id in unitIdMap: continue
            unitTreeId = self._insertToTree(unitView, selectedYear)
            unitIdMap[unitView.id] = unitTreeId
            while unitView.composite_unit_id != None:
                if unitView.composite_unit_id in unitIdMap:
                    parentTreeId = unitIdMap[unitView.composite_unit_id]
                    self._armyList.move(unitTreeId, parentTreeId, 0)
                    break
                else:
                    parentUnitView = self._troopManagerModel.get_unit_view(unitView.composite_unit_id, selectedYear)
                    parentTreeId = self._insertToTree(parentUnitView, selectedYear)
                    unitIdMap[parentUnitView.id] = parentTreeId
                    self._armyList.move(unitTreeId, parentTreeId, 0)
                    unitView = parentUnitView
        if selectedUnit and selectedUnit in unitIdMap:
            self._armyList.selection_set([unitIdMap[selectedUnit]])
            
        
    def _fillTreeFlat(self, selectUnit=None, selectedYear=None):
        self._armyList.delete(*self._armyList.get_children())
        
        unitIdList = self._troopManagerModel.get_unit_list(selectedYear)
        for unitId in unitIdList:
            unitView = self._troopManagerModel.get_unit_view(unitId, selectedYear)
            if self._displayDeadVar.get() == 0 and unitView.is_dead: continue
            self._insertToTree(unitView, selectedYear)
        
    def _newGame(self):
        if self._troopManagerModel:
            if askyesno('Close Current Game', 'A game database is already in use. Close it?'):
                self._troopManagerModel = None
            else:
                showinfo('Cancelled', 'New game has been cancelled')
                return
                
        while not self._troopManagerModel:
            gameDbFilename = asksaveasfilename(initialdir = ".",title = "Game database filename",filetypes = (("DatabaseFiles","*.db"),("all files","*.*")))
            if not gameDbFilename:
                showinfo('Cancelled', 'New game has been cancelled')
                return
            gameDb = sqlite3.connect(gameDbFilename)
            
            self._troopManagerModel = CivTroopManager(gameDb)
            self._strengthModel = ComputeStrength(self._troopManagerModel, self._game_data)
            
    def _openGame(self):
        if self._troopManagerModel:
            if askyesno('Close Current Game', 'A game database is already in use. Close it?'):
                self._troopManagerModel = None
            else:
                showinfo('Cancelled', 'Open game has been cancelled')
                return
        filename = askopenfilename(initialdir = ".",title = "Select Game DB",filetypes = (("Database Files","*.db"),("all files","*.*")))
        if not filename:
            showinfo('Cancelled', 'Open game has been cancelled')
            return
        self._openDatabase(filename)
        
    def _saveUnitDb(self):
        self._game_data.save()
        showinfo("Saved", "Civ Game Data Saved")
        
    def _exit(self):
        import sys
        sys.exit(0)
        
    def _createUnit(self):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        unitTypes = self._game_data.get_unit_types()
        if not unitTypes:
            showinfo("Not Ready", "No unit types defined.")
            return
        unitTypes = list(map(lambda info: info[1], unitTypes))
        CreateUnitDialog(self._root, self._troopManagerModel, self._game_data, 
                            yearHint=self._getYear(),
                            onOk=self._fillTree,
                            onContinue=self._createUnitWizard)
                            
    def _createUnitWizard(self, selectedUnitId, year):
        unitView = self._troopManagerModel.get_unit_view(selectedUnitId, display_key=self._display_key)
        if unitView.unit_type == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
            return self._assignMetaUnit(selectedUnitId, year)
        else:
            return self._promoteUnit(selectedUnitId, year, lambda promotedUnitId: self._assignMetaUnit(promotedUnitId))

    def _getCompositePromotionsString(self, topUnitId, recursiveData=None):
        unitView = self._troopManagerModel.get_unit_view(topUnitId, display_key=self._display_key)
        if recursiveData == None:
            promotionData = {}
        else: promotionData = recursiveData
        for promotion in unitView.display.promotions:
            promotionData[promotion] = promotionData.get(promotion, 0) + 1
        for subUnitId in unitView.subordinate_units:
            self._getCompositePromotionsString(subUnitId, promotionData)
        if recursiveData == None:
            # top level. Produce string
            s = ""
            for promotion, promotionCount in promotionData.items():
                s += "\t%s: %d\n" % (promotion, promotionCount)
            return s
            
    def _getCompositeHistoryString(self, topUnitId, recursiveData=None):
        unitView = self._troopManagerModel.get_unit_view(topUnitId, display_key=self._display_key)
        unit_view_in_year = lambda y: self._troopManagerModel.get_unit_view(topUnitId, y, display_key=self._display_key)
        if recursiveData == None:
            historyData = []
        else: historyData = recursiveData
        for historyRecord in unitView.display.history:
            eventId, year, note = historyRecord
            historyData.append((year, eventId, note, unit_view_in_year(year).display.name))
        for subUnitId in unitView.subordinate_units:
            self._getCompositeHistoryString(subUnitId, historyData)
        if recursiveData == None:
            # top level. Produce string
            s = ""
            historyData.sort() # Should sort on year
            for historyRecord in historyData:
                year, eventId, note, unitName = historyRecord
                s += "\t%d: Unit %s. %s (event %d)\n" % (year, unitName, note, eventId)
            #print("composite history string:\n" + s)
            return s
    
    def _getCompositeSubunitString(self, topUnitId, prefix="\t"):
        unitView = self._troopManagerModel.get_unit_view(topUnitId, display_key=self._display_key)
        s = ""
        for subUnitId in unitView.subordinate_units:
            s += "%s%s\n" % (prefix, self._troopManagerModel.get_unit_view(subUnitId).name)
            s += self._getCompositeSubunitString(subUnitId, prefix+"\t")
        return s
        
    def _getCompositeVictoryCountAndString(self, topUnitId, recursiveData=None):
        unitView = self._troopManagerModel.get_unit_view(topUnitId, display_key=self._display_key)
        if recursiveData == None:
            victoryData = {}
        else: victoryData = recursiveData
        for victoryYear, enemyUnitType, enemyUnitOwner, enemyUnitName in unitView.display.victories:
            victoryData[enemyUnitType] = victoryData.get(enemyUnitType, 0) + 1
            victoryData[enemyUnitOwner] = victoryData.get(enemyUnitOwner, 0) + 1
        for subUnitId in unitView.subordinate_units:
            self._getCompositeVictoryCountAndString(subUnitId, victoryData)
        if recursiveData == None:
            # top level. Produce string and count
            victoryCount = 0
            s = ""
            for defeatedUnitType, defeatedUnitTypeVictoryCount in victoryData.items():
                s += "\t%s: %d\n" % (defeatedUnitType, defeatedUnitTypeVictoryCount)
                victoryCount += defeatedUnitTypeVictoryCount
            return victoryCount/2, s
            
    def _viewDetails(self, selectedUnitId=None, yearHint=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
            
        top = Toplevel(self._root)
        sc = ScrolledText(top, width=100)
        detailsTemplate = """
Unit '%(name)s'
------------------
TYPE          : %(type)s
COMPOSITE UNIT: %(composite)s
LOCATION      : %(location)s
HEADQUARTERS  : %(hq)s
VICTORIES     : %(victoryCount)d
%(victories)s
PROMOTIONS    : 
%(promotions)s
SUB UNITS     :
%(subunits)s
HISTORY       :
%(history)s
"""
        details = {}
        unitView = self._troopManagerModel.get_unit_view(selectedUnitId, yearHint, display_key=self._display_key)
        compositeUnitId = unitView.composite_unit_id
        if compositeUnitId != None:
            compositeUnit = self._troopManagerModel.get_unit_view(compositeUnitId, yearHint, display_key=self._display_key).display.name
        else:
            compositeUnit = "<None>"
        victoryCount, victoryString = self._getCompositeVictoryCountAndString(unitView.id)
        details = {
            "name": unitView.display.name,
            "type": unitView.display.unit_type,
            "composite": compositeUnit,
            "location": unitView.display.location,
            "victoryCount": victoryCount,
            "victories": victoryString,
            "hq": unitView.display.HQ,
            "promotions": self._getCompositePromotionsString(unitView.id),
            "subunits": self._getCompositeSubunitString(unitView.id),
            "history": self._getCompositeHistoryString(unitView.id)
        }
        sc.insert('insert', detailsTemplate % details)
        sc.grid(row=0, column=0, sticky="nsew")
        
    def _assignMetaUnit(self, selectedUnitId=None, yearHint=None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if yearHint == None:
            yearHint = self._getYear()
        unitIds = self._troopManagerModel.getUnitList(yearHint)
        if not unitIds:
            showinfo("Not Ready", "No units defined.")
            return
        compositeUnits = []
        for unitId  in unitIds:
            unitView = self._troopManagerModel.get_unit_view(unitId, yearHint, display_key=self._display_key)
            if not unitView.is_dead and unitView.unit_type == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
                compositeUnits.append(unitId)
        if not compositeUnits:
            showinfo("Not Ready", "No composite units defined.")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return

        AssignUnitDialog(self._root, selectedUnitId, compositeUnits, self._troopManagerModel, self._game_data,yearHint=yearHint,
                            onOk=self._fillTree,
                            onContinue=onContinue)
        
    def _moveUnit(self, selectedUnitId=None, yearHint=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        
        MoveUnitDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data,yearHint=yearHint,
                        onOk=self._fillTree)
                        
    def _renameUnit(self, selectedUnitId=None, yearHint=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        
        RenameUnitDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data,yearHint=yearHint,
                        onOk=self._fillTree)
                        
    def _transferUnitHq(self, selectedUnitId=None, yearHint=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        
        TransferHQDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data,yearHint=yearHint,
                        onOk=self._fillTree)
        
    def _upgradeUnit(self, selectedUnitId=None, yearHint=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
            
        unitView = self._troopManagerModel.get_unit_view(selectedUnitId, display_key=self._display_key)
        if unitView.unit_type == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
            showinfo("Error", "Cannot upgrade a composite unit")
            return
        
        UpgradeUnitDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data, yearHint=yearHint,
                        onOk=self._fillTree)
        
    def _promoteUnit(self, selectedUnitId = None, yearHint=None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        PromoteUnitDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data,
                            yearHint = yearHint,
                            onOk=self._fillTree,
                            onContinue=onContinue)
        
    def _destroyUnit(self, selectedUnitId=None, yearHint=None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        DestroyUnitDialog(self._root, selectedUnitId, self._troopManagerModel,self._game_data,
                            yearHint = yearHint,
                            onOk=self._fillTree,
                            onContinue=onContinue)
                            
    def _recordUnitHistory(self, selectedUnitId=None, yearHint=None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        RecordUnitHistoryDialog(self._root, selectedUnitId, self._troopManagerModel,self._game_data,
                            yearHint = yearHint,
                            onOk=self._fillTree,
                            onContinue=onContinue)
                            
    def _recordUnitVictory(self, selectedUnitId=None, yearHint=None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        RecordVictoryDialog(self._root, selectedUnitId, self._troopManagerModel,self._game_data,
                            yearHint = yearHint,
                            onOk=self._fillTree,
                            onContinue=onContinue)
                            
    def _deleteUnitEvent(self, selectedUnitId = None, yearHint = None, onContinue=None):
        if not self._troopManagerModel:
            showinfo("Not Ready", "No Open Database")
            return
        if not selectedUnitId:
            selectedUnitId = self._getSelectedUnit()
        if not selectedUnitId:
            showinfo('Not Ready', "No unit selected to assign")
            return
        if yearHint == None:
            yearHint = self._getYear()
        DeleteUnitEventDialog(self._root, selectedUnitId, self._troopManagerModel, self._game_data,
                                yearHint = yearHint,
                                onOk=self._fillTree,
                                onContinue=onContinue)
        
    def _createUnitType(self):
        CreateOrEditUnitTypeDialog(self._root, self._game_data, edit=False)
        
    def _editUnitType(self):
        CreateOrEditUnitTypeDialog(self._root, self._game_data, edit=True)
        
    def _createPromotionType(self):
        CreateOrEditPromotionTypeDialog(self._root, self._game_data, edit=False)
        
    def _editPromotionType(self):
        CreateOrEditPromotionTypeDialog(self._root, self._game_data, edit=True)
        
        
if __name__=="__main__":
    if len(sys.argv) > 1:
        dbName = sys.argv[1]
        manager = Civ4TroopManager_tkinterView(dbName, game_data_file="civgamedata.json")
    else:
        manager = Civ4TroopManager_tkinterView(game_data_file="civgamedata.json")
    manager.mainLoop()