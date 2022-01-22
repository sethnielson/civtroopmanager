#!/usr/bin/python
# REQUIRES PYTHON 3.0!

from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from tkinter.messagebox import *
from tkinter.filedialog import askopenfilename, asksaveasfilename
from c4tm_model import Civ4UnitTypeManager, Civ4TroopManager
import sqlite3

def entrySet(entry, text):
	entry.delete(0, END)
	entry.insert(0, text)
	
def capitalizeFirst(s):
	return s[0].upper()+s[1:]

class ComputeStrength(object):
	def __init__(self, manager):
		self.manager = manager
		
	def unitTypeStrength(self, unitType):
		unitTypeData = self.manager.getUnitTypeManager().getUnitTypes(unitTypeName=unitType)
		if not unitTypeData:
			raise Exception("No Such UnitType")
		return unitTypeData[0][2]
		
	def aggregateStrength(self, unitView, year=None):
		if unitView.unitType == self.manager.COMPOSITE_UNIT_TYPE:
			aggregateStrength = 0
			for subUnit in unitView.subordinateUnits:
				subUnitView = self.manager.getUnitView(subUnit, year)
				aggregateStrength += self.aggregateStrength(subUnitView, year)
		else:
			aggregateStrength = self.unitTypeStrength(unitView.unitType)
		return aggregateStrength
		
	def averageStrength(self, unitView, year=None):
		if unitView.unitType == self.manager.COMPOSITE_UNIT_TYPE:
			subUnitCount = len(unitView.subordinateUnits)
			if subUnitCount == 0: return 0
			
			aggregateStrength = self.aggregateStrength(unitView, year)
			averageStrength = aggregateStrength / float(subUnitCount)
		else:
			averageStrength = self.unitTypeStrength(unitView.unitType)
		return averageStrength
		
	def composite(self, unitView, year=None):
		if unitView.unitType == self.manager.COMPOSITE_UNIT_TYPE:
			return "%d (%0.2f/%d)" % (self.aggregateStrength(unitView, year), 
									self.averageStrength(unitView, year), 
									len(unitView.subordinateUnits))
		else:
			return "%d%s" % (self.aggregateStrength(unitView, year), "+"*len(unitView.promotions))
		

class SelectionBox(object):
	def __init__(self, parent, label, items):
		self._items = items
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
		self._selectBox.insert(0, *items)
		self._selectBox.bind("<Key>", self._jumpToSelect)
		self._selectBox.bind("<<ListboxSelect>>", self._setSelectedLabel)
		self._selectBox.activate(0)
		self._setActiveSelected()
		self._selectBox.pack(fill=BOTH, expand=1)
		selectFrame.pack(fill=BOTH, expand=1)
		
		scrollbar.config(command=self._selectBox.yview)
		
	def selected(self):
		return self._selectedVar.get()
	
	def _setSelectedLabel(self, event):
		curselection = self._selectBox.curselection()
		if len(curselection) != 1:
			# this shouldn't happen. Maybe an exception? For now, just ignore.
			return
		selectedText = self._selectBox.get(curselection[0])
		self._selectedVar.set(selectedText)
		
	def _setActiveSelected(self):
		curselection = self._selectBox.curselection()
		if curselection:
			self._selectBox.select_clear(curSelected[0], curSelected[-1])
		self._selectBox.select_set(ACTIVE)
		self._setSelectedLabel(None)
		
	def _jumpToSelect(self, event):
		letterPressed = event.char
		if "a" <= letterPressed <= "z":
			letterIndices = []
			for i in range(len(self._items)):
				item = self._items[i]
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
		
	def _insertButtonFrame(self, parent=None):
		if parent == None:
			parent = self.top
		buttonFrame = Frame(parent)
		b = Button(buttonFrame, text="Save", command=self.ok)
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
	def __init__(self, parent, unitTypes, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(CreateUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unitTypes = unitTypes
		
		unitTypes.append("--CompositeUnit--")
		unitTypes.sort()
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
		
		self.unitTypeSelect = SelectionBox(top, "Unit Type:", unitTypes)
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
		
		cp = self.manager.setDbCheckpoint()
		try:
			
			unitType = self.unitTypeSelect.selected()
			if unitType == "--CompositeUnit--":
				unitType = self.manager.COMPOSITE_UNIT_TYPE
			unitId = self.manager.createUnit(year, unitType, self.locationEntry.get())
			self.manager.renameUnit(unitId, year, self.nameEntry.get())
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (unitId, year)
			

		
class PromoteUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, promotionTypes, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(PromoteUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Promote '%s'." % self.unitView.name).pack()
		
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
		self.promotionDisplay.insert(0, *self.unitView.promotions)
		self.promotionDisplay.pack(fill=BOTH, expand=1)
		displayFrame.pack(fill=BOTH, expand=1)
		
		availablePromotions = []
		for promotion in promotionTypes:
			if promotion not in self.unitView.promotions:
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
		cp = self.manager.setDbCheckpoint()
		try:
			for selectionIndex in curselection:
				promotion = self.promotionSelect.get(selectionIndex)
				self.manager.promoteUnit(self.unit, year, promotion)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo("Database Error", str(e))
			return "retry", None
		return "ok", (self.unit, year)
		
class UpgradeUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, unitTypes, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(UpgradeUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Upgrade '%s'." % self.unitView.name).pack()
		
		Label(top, text="Year (negative for BC):").pack()
		self.yearEntry = Entry(top)
		if yearHint != None:
			entrySet(self.yearEntry, yearHint)
		self.yearEntry.pack(padx=5)
		
		self.unitTypeSelect = SelectionBox(top, "Upgrade Unit Type:", unitTypes)
		self.unitTypeSelect.frame.pack()

		self._insertButtonFrame()
		
	def _ok(self):
		try:
			year = int(self.yearEntry.get())
		except:
			showinfo('Error', "Invalid year '%s'" % self.yearEntry.get())
			return "retry", None
			
		unitType = self.unitTypeSelect.selected()
		if not unitType:
			showinfo("Error", "No Upgrade Type Selected")
			return "retry", None
		
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.upgradeUnit(self.unit, year, unitType)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, year)
		
class MoveUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(MoveUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager
		unitView = self.manager.getUnitView(unit, yearHint)
		subUnitViews = list(map(lambda subId: self.manager.getUnitView(subId, yearHint), unitView.subordinateUnits))
		queuePointer = 0
		while len(subUnitViews) > queuePointer:
			nextUnitView = subUnitViews[queuePointer]
			subUnitViews += nextUnitView.subordinateUnits
			queuePointer += 1
		subUnits = []
		self.subUnitNames = {}
		for subUnitView in subUnitViews:
			compositeUnit = self.manager.getUnitView(subUnitView.compositeUnitId, yearHint).name
			displayName = "%d. %s: %s (%s)" % (subUnitView.id, subUnitView.name, compositeUnit, subUnitView.location)
			subUnits.append(displayName)
			self.subUnitNames[displayName] = subUnitView.id

		top = self.top
		
		if self.unitView.unitType == manager.COMPOSITE_UNIT_TYPE:
			Label(top, text="Set deployment location of composite unit '%s'." % self.unitView.name).pack()
		else:
			Label(top, text="Set physical location of civ unit '%s'." % self.unitView.name).pack()
		
		Label(top, text="Year (negative for BC):").pack()
		self.yearEntry = Entry(top)
		if yearHint != None:
			entrySet(self.yearEntry, yearHint)
		self.yearEntry.pack(padx=5)
		
		Label(top, text="Current location is '%s'. Enter new location:" % self.unitView.location).pack()
		self.locationEntry = Entry(top)
		self.locationEntry.pack(padx=5)
		
		if subUnits:
			Label(top, text="Select subunits deploying with '%s' to new location." % self.unitView.name).pack()
		
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.moveUnit(self.unit, year, newLocation)
			if self.subUnitNames:
				for selectionIndex in self.subunitDisplay.curselection():
					displayName = self.subunitDisplay.get(selectionIndex)
					subUnit = self.subUnitNames[displayName]
					self.manager.moveUnit(subUnit, year, newLocation)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo("Database Error", str(e))
			return "retry", None
		return "ok", (self.unit, year)
		
		
class TransferHQDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(TransferHQDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Move Headquarters for '%s'." % self.unitView.name).pack()
		
		Label(top, text="Year (negative for BC):").pack()
		self.yearEntry = Entry(top)
		if yearHint != None:
			entrySet(self.yearEntry, yearHint)
		self.yearEntry.pack(padx=5)
		
		Label(top, text="Current HQ is '%s'. Enter new HQ:" % self.unitView.HQ).pack()
		self.hqEntry = Entry(top)
		self.hqEntry.pack(padx=5)
		
		subUnits = []
		self.subUnitNames = {}
		for subUnit in self.unitView.subordinateUnits:
			subUnitView = manager.getUnitView(subUnit, yearHint)
			if subUnitView.unitType != manager.COMPOSITE_UNIT_TYPE:
				displayName = "%d. %s (%s)" % (subUnitView.id, subUnitView.name, subUnitView.HQ)
				subUnits.append(displayName)
				self.subUnitNames[displayName] = subUnitView.id
		
		if subUnits:
			Label(top, text="Select immediate subordinate civ units changing HQ with '%s'." % self.unitView.name).pack()
		
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.transferUnitHq(self.unit, year, newHQ)
			if self.subUnitNames:
				for selectionIndex in self.subunitDisplay.curselection():
					displayName = self.subunitDisplay.get(selectionIndex)
					subUnit = self.subUnitNames[displayName]
					self.manager.transferUnitHq(subUnit, year, newHQ)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo("Database Error", str(e))
			return "retry", None
		return "ok", (self.unit, year)
		
class RenameUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(RenameUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Rename '%s'." % self.unitView.name).pack()
		
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.renameUnit(self.unit, year, newName)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo("Database Error", str(e))
			return "retry", None
		return "ok", (self.unit, year)
		
class AssignUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, compositeUnits, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(AssignUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.compositeUnitViews = map(lambda cId: manager.getUnitView(cId, yearHint), compositeUnits)
		self.manager = manager

		top = self.top
		
		Label(top, text="Assign '%s' to Metaunit." % self.unitView.name).pack()
		
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
			displayName = "%d. %s" % (compositeUnitView.id, compositeUnitView.name)
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
		cp = self.manager.setDbCheckpoint()
		try:
			
			compositeUnitDisplayName = self.compositeUnitSelect.selected()
			compositeUnitId = self.compositeUnitLookup[compositeUnitDisplayName]
			self.manager.assignUnitToComposite(self.unit, year, compositeUnitId)
			if self.transferHqVar.get() == 1:
				compositeUnitView = self.manager.getUnitView(compositeUnitId, year)
				self.manager.transferUnitHq(self.unit, year, compositeUnitView.HQ)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, year)

class DeleteUnitEventDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(DeleteUnitEventDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Delete event from '%s' (%d) history. CANNOT BE UNDONE!" % (self.unitView.name, unit)).pack()
		
		self.yearHint = yearHint
		
		unitEvents = []
		self.unitEventMapping = {}
		for eventData in self.unitView.history:
			eventId, eventYear, eventNote = eventData
			displayName = "%d. %s (event id %d)" % (eventYear, eventNote, eventId)
			unitEvents.append(displayName)
			self.unitEventMapping[displayName] = eventId
		unitEvents.reverse()
		self.unitEventSelect = SelectionBox(top, "Unit Events as of year %d" % yearHint, unitEvents)
		self.unitEventSelect.frame.pack()
		
		self._insertButtonFrame()

	def _ok(self):
		selectedEvent = self.unitEventSelect.selected()
		if not selectedEvent:
			showinfo('Error', 'No Event Selected')
			return "retry", None
		selectedEventId = self.unitEventMapping[selectedEvent]
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.deleteEvent(selectedEventId)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, self.yearHint)
		
class DestroyUnitDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(DestroyUnitDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Destroy unit '%s'." % self.unitView.name).pack()
		
		Label(top, text="Year (negative for BC):").pack()
		self.yearEntry = Entry(top)
		if yearHint != None:
			entrySet(self.yearEntry, yearHint)
		else:
			yearHint = "most recent"
		self.yearEntry.pack(padx=5)
		
		unitTypes = self.manager.getUnitTypeManager().getUnitTypes()
		unitTypes = list(map(lambda info: info[1], unitTypes))
		self.unitDestroyerSelect = SelectionBox(top, "Select unit type that destroyed '%s' (optional)" % self.unitView.name, unitTypes)
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.destroyUnit(self.unit, year, destroyerUnitType, destroyerOwner, destroyerName)
			if details:
				self.manager.unitHistory(self.unit, year, details)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, year)
		
class RecordUnitHistoryDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(RecordUnitHistoryDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="New history event for unit '%s'." % self.unitView.name).pack()
		
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.unitHistory(self.unit, year, details)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, year)
		
class RecordVictoryDialog(OkCancelContinueDialog):
	def __init__(self, parent, unit, manager, yearHint=None, onOk=None, onCancel=None, onContinue=None):
		super(RecordVictoryDialog, self).__init__(parent, onOk, onCancel, onContinue)
		self.unit = unit
		self.unitView = manager.getUnitView(unit, yearHint)
		self.manager = manager

		top = self.top
		
		Label(top, text="Record victory for unit '%s'." % self.unitView.name).pack()
		
		Label(top, text="Year (negative for BC):").pack()
		self.yearEntry = Entry(top)
		if yearHint != None:
			entrySet(self.yearEntry, yearHint)
		else:
			yearHint = "most recent"
		self.yearEntry.pack(padx=5)
		
		unitTypes = self.manager.getUnitTypeManager().getUnitTypes()
		unitTypes = list(map(lambda info: info[1], unitTypes))
		self.unitDestroyedSelect = SelectionBox(top, "Select unit type that '%s' destroyed" % self.unitView.name, unitTypes)
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
		cp = self.manager.setDbCheckpoint()
		try:
			self.manager.unitVictory(self.unit, year, destroyedUnitType, destroyedUnitOwner, destroyedUnitName)
			if details:
				self.manager.unitHistory(self.unit, year, details)
		except Exception as e:
			self.manager.revertToCheckpoint(cp)
			showinfo('Database Error', str(e))
			return "close", None
		return "ok", (self.unit, year)
		
class CreateUnitTypeDialog(object):
	def __init__(self, parent, manager):
		self.manager = manager

		top = self.top = Toplevel(parent)
		
		Label(top, text="Unit Type Name:").pack()
		self.nameEntry = Entry(top)
		self.nameEntry.pack(padx=5)
		
		Label(top, text="Strength:").pack()
		self.strengthEntry = Entry(top)
		self.strengthEntry.pack(padx=5)
		
		b = Button(top, text="OK", command=self.ok)
		b.pack(pady=5)
		
	def _ok(self):
		try:
			strength = int(self.strengthEntry.get())
			if strength < 0:
				raise Exception()
		except:
			showinfo('Error', "Invalid strength '%s'" % self.yearEntry.get())
			return
			
		if not self.nameEntry.get():
			showinfo('Error', "No unit name specified.")
			return
		
		try:
			self.manager.createUnitType(self.nameEntry.get(), strength)
		except Exception as e:
			showinfo('Error', str(e))
			return
			
	def ok(self):
		self._ok()
		self.top.destroy()
		
class CreatePromotionTypeDialog(object):
	def __init__(self, parent, manager):
		self.manager = manager

		top = self.top = Toplevel(parent)
		
		Label(top, text="Promotion Type Name:").pack()
		self.nameEntry = Entry(top)
		self.nameEntry.pack(padx=5)
		
		b = Button(top, text="OK", command=self.ok)
		b.pack(pady=5)
		
	def _ok(self):
			
		if not self.nameEntry.get():
			showinfo('Error', "No unit name specified.")
			return "retry"
		
		try:
			self.manager.addPromotionType(self.nameEntry.get())
		except Exception as e:
			showinfo('Error', str(e))
			return "retry"
		return "ok"
			
	def ok(self):
		res = self._ok()
		if res == "ok":
			self.top.destroy()

class Civ4TroopManager_tkinterView(object):
	def __init__(self, databaseName=None):
		self._troopManagerModel = None
		self._strengthModel = None
		self.initView()
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
		Name	Type	HQ	Location	Strength
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
		filemenu.add_command(label="Save Unit DB", command=self._saveUnitDb)
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
		self._troopManagerModel = Civ4TroopManager(gameDb)
		self._strengthModel = ComputeStrength(self._troopManagerModel)
		self._fillTree()
		
	def _getSelectedUnit(self):
		curTreeSelections = self._armyList.selection()
		if len(curTreeSelections) == 1:
			return self._armyList.item(curTreeSelections[0])["text"]
		else:
			return None
			
	def _getYear(self):
		minYear, maxYear = self._troopManagerModel.getMinMaxYears()
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
		return self._armyList.insert("" , 0, text=unitView.id, 
									values=(
										unitView.name, 
										unitView.unitType, 
										unitView.HQ, 
										unitView.location,
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
		
		unitIdList = self._troopManagerModel.getUnitList(selectedYear)
		unitIdMap = {}
		for unitId in unitIdList:
			unitView = self._troopManagerModel.getUnitView(unitId, selectedYear)
			if self._displayDeadVar.get() == 0 and unitView.isDead: continue
			if unitView.id in unitIdMap: continue
			unitTreeId = self._insertToTree(unitView, selectedYear)
			unitIdMap[unitView.id] = unitTreeId
			while unitView.compositeUnitId != None:
				if unitView.compositeUnitId in unitIdMap:
					parentTreeId = unitIdMap[unitView.compositeUnitId]
					self._armyList.move(unitTreeId, parentTreeId, 0)
					break
				else:
					parentUnitView = self._troopManagerModel.getUnitView(unitView.compositeUnitId, selectedYear)
					parentTreeId = self._insertToTree(parentUnitView, selectedYear)
					unitIdMap[parentUnitView.id] = parentTreeId
					self._armyList.move(unitTreeId, parentTreeId, 0)
					unitView = parentUnitView
		if selectedUnit and selectedUnit in unitIdMap:
			self._armyList.selection_set([unitIdMap[selectedUnit]])
			
		
	def _fillTreeFlat(self, selectUnit=None, selectedYear=None):
		self._armyList.delete(*self._armyList.get_children())
		
		unitIdList = self._troopManagerModel.getUnitList(selectedYear)
		for unitId in unitIdList:
			unitView = self._troopManagerModel.getUnitView(unitId, selectedYear)
			if self._displayDeadVar.get() == 0 and unitView.isDead: continue
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
				
			if askyesno('New Game', 'Initialize game database with an existing unit database?'):
				filename = askopenfilename(initialdir = ".",title = "Select Unit DB",filetypes = (("Database Files","*.db"),("all files","*.*")))
				if not filename:
					continue
				unitDb = sqlite3.connect(filename)
				unitTypeManager = Civ4UnitTypeManager(unitDb)
				unitTypeManager.cloneTo(gameDb)
			
			self._troopManagerModel = Civ4TroopManager(gameDb)
			self._strengthModel = ComputeStrength(self._troopManagerModel)
			
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
		showinfo('Save Unit DB', 'Not Yet Implemented')
		
	def _exit(self):
		import sys
		sys.exit(0)
		
	def _createUnit(self):
		if not self._troopManagerModel:
			showinfo("Not Ready", "No Open Database")
			return
		unitTypes = self._troopManagerModel.getUnitTypeManager().getUnitTypes()
		if not unitTypes:
			showinfo("Not Ready", "No unit types defined.")
			return
		unitTypes = list(map(lambda info: info[1], unitTypes))
		CreateUnitDialog(self._root, unitTypes, self._troopManagerModel, yearHint=self._getYear(),
							onOk=self._fillTree,
							onContinue=self._createUnitWizard)
							
	def _createUnitWizard(self, selectedUnitId, year):
		unitView = self._troopManagerModel.getUnitView(selectedUnitId)
		if unitView.unitType == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
			return self._assignMetaUnit(selectedUnitId, year)
		else:
			return self._promoteUnit(selectedUnitId, year, lambda promotedUnitId: self._assignMetaUnit(promotedUnitId))

	def _getCompositePromotionsString(self, topUnitId, recursiveData=None):
		unitView = self._troopManagerModel.getUnitView(topUnitId)
		if recursiveData == None:
			promotionData = {}
		else: promotionData = recursiveData
		for promotion in unitView.promotions:
			promotionData[promotion] = promotionData.get(promotion, 0) + 1
		for subUnitId in unitView.subordinateUnits:
			self._getCompositePromotionsString(subUnitId, promotionData)
		if recursiveData == None:
			# top level. Produce string
			s = ""
			for promotion, promotionCount in promotionData.items():
				s += "\t%s: %d\n" % (promotion, promotionCount)
			return s
			
	def _getCompositeHistoryString(self, topUnitId, recursiveData=None):
		unitView = self._troopManagerModel.getUnitView(topUnitId)
		if recursiveData == None:
			historyData = []
		else: historyData = recursiveData
		for historyRecord in unitView.history:
			eventId, year, note = historyRecord
			historyData.append((year, eventId, note, unitView.name))
		for subUnitId in unitView.subordinateUnits:
			self._getCompositeHistoryString(subUnitId, historyData)
		if recursiveData == None:
			# top level. Produce string
			s = ""
			historyData.sort() # Should sort on year
			for historyRecord in historyData:
				year, eventId, note, unitName = historyRecord
				s += "\t%d: Unit %s. %s (event %d)\n" % (year, unitName, note, eventId)
			print("composite history string:\n" + s)
			return s
	
	def _getCompositeSubunitString(self, topUnitId, prefix="\t"):
		unitView = self._troopManagerModel.getUnitView(topUnitId)
		s = ""
		for subUnitId in unitView.subordinateUnits:
			s += "%s%s\n" % (prefix, self._troopManagerModel.getUnitView(subUnitId).name)
			s += self._getCompositeSubunitString(subUnitId, prefix+"\t")
		return s
		
	def _getCompositeVictoryCountAndString(self, topUnitId, recursiveData=None):
		unitView = self._troopManagerModel.getUnitView(topUnitId)
		if recursiveData == None:
			victoryData = {}
		else: victoryData = recursiveData
		for victoryYear, enemyUnitType, enemyUnitOwner, enemyUnitName in unitView.victories:
			victoryData[enemyUnitType] = victoryData.get(enemyUnitType, 0) + 1
			victoryData[enemyUnitOwner] = victoryData.get(enemyUnitOwner, 0) + 1
		for subUnitId in unitView.subordinateUnits:
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
		sc = ScrolledText(top)
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
		unitView = self._troopManagerModel.getUnitView(selectedUnitId, yearHint)
		compositeUnitId = unitView.compositeUnitId
		if compositeUnitId != None:
			compositeUnit = self._troopManagerModel.getUnitView(compositeUnitId, yearHint).name
		else:
			compositeUnit = "<None>"
		victoryCount, victoryString = self._getCompositeVictoryCountAndString(unitView.id)
		details = {
			"name": unitView.name,
			"type": unitView.unitType,
			"composite": compositeUnit,
			"location": unitView.location,
			"victoryCount": victoryCount,
			"victories": victoryString,
			"hq": unitView.HQ,
			"promotions": self._getCompositePromotionsString(unitView.id),
			"subunits": self._getCompositeSubunitString(unitView.id),
			"history": self._getCompositeHistoryString(unitView.id)
		}
		sc.insert('insert', detailsTemplate % details)
		sc.pack()
		
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
			unitView = self._troopManagerModel.getUnitView(unitId, yearHint)
			if not unitView.isDead and unitView.unitType == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
				compositeUnits.append(unitId)
		if not compositeUnits:
			showinfo("Not Ready", "No composite units defined.")
			return
		if not selectedUnitId:
			selectedUnitId = self._getSelectedUnit()
		if not selectedUnitId:
			showinfo('Not Ready', "No unit selected to assign")
			return

		AssignUnitDialog(self._root, selectedUnitId, compositeUnits, self._troopManagerModel, yearHint=yearHint,
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
		
		MoveUnitDialog(self._root, selectedUnitId, self._troopManagerModel, yearHint=yearHint,
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
		
		RenameUnitDialog(self._root, selectedUnitId, self._troopManagerModel, yearHint=yearHint,
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
		
		TransferHQDialog(self._root, selectedUnitId, self._troopManagerModel, yearHint=yearHint,
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
			
		unitView = self._troopManagerModel.getUnitView(selectedUnitId)
		if unitView.unitType == self._troopManagerModel.COMPOSITE_UNIT_TYPE:
			showinfo("Error", "Cannot upgrade a composite unit")
			return
		
		unitTypes = self._troopManagerModel.getUnitTypeManager().getUnitTypes()
		unitTypes = list(map(lambda info: info[1], unitTypes))
		unitTypes.remove(unitView.unitType)
		
		if not unitTypes:
			showinfo("Not Ready", "No upgrades available.")
			return
		
		UpgradeUnitDialog(self._root, selectedUnitId, unitTypes, self._troopManagerModel, yearHint=yearHint,
						onOk=self._fillTree)
		
	def _promoteUnit(self, selectedUnitId = None, yearHint=None, onContinue=None):
		if not self._troopManagerModel:
			showinfo("Not Ready", "No Open Database")
			return
		promotionTypes = self._troopManagerModel.getUnitTypeManager().getPromotionTypes()
		if not promotionTypes:
			showinfo("Not Ready", "No promotion types defined.")
			return
		promotionTypes = list(map(lambda info: info[1], promotionTypes))
		if not selectedUnitId:
			selectedUnitId = self._getSelectedUnit()
		if not selectedUnitId:
			showinfo('Not Ready', "No unit selected to assign")
			return
		if yearHint == None:
			yearHint = self._getYear()
		PromoteUnitDialog(self._root, selectedUnitId, promotionTypes, self._troopManagerModel, 
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
		DestroyUnitDialog(self._root, selectedUnitId, self._troopManagerModel,
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
		RecordUnitHistoryDialog(self._root, selectedUnitId, self._troopManagerModel,
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
		RecordVictoryDialog(self._root, selectedUnitId, self._troopManagerModel,
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
		DeleteUnitEventDialog(self._root, selectedUnitId, self._troopManagerModel,
								yearHint = yearHint,
								onOk=self._fillTree,
								onContinue=onContinue)
		
	def _createUnitType(self):
		if not self._troopManagerModel:
			showinfo("Not Ready", "No Open Database")
			return
		CreateUnitTypeDialog(self._root, self._troopManagerModel.getUnitTypeManager())
		
	def _editUnitType(self):
		showinfo('Save Unit DB', 'Not Yet Implemented')
		
	def _createPromotionType(self):
		if not self._troopManagerModel:
			showinfo("Not Ready", "No Open Database")
			return
		CreatePromotionTypeDialog(self._root, self._troopManagerModel.getUnitTypeManager())
		
	def _editPromotionType(self):
		showinfo('Save Unit DB', 'Not Yet Implemented')
		
		
if __name__=="__main__":
	if len(sys.argv) > 1:
		dbName = sys.argv[1]
		manager = Civ4TroopManager_tkinterView(dbName)
	else:
		manager = Civ4TroopManager_tkinterView()
	manager.mainLoop()