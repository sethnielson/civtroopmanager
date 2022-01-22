#!/usr/bin/python
import sqlite3

class DbKeyLookup(object):
	NOTFOUND = object()
	def __init__(self, db, tableName, keyColumnNames, valueColumnNames, raiseIfNotFound=False):
		self._db = db
		self._tableName = tableName
		self._keyColumnNames = keyColumnNames
		self._valueColumnNames = valueColumnNames
		self._raiseIfNotFound = raiseIfNotFound
		self._sql = "SELECT "
		self._sql += "%s FROM " % ", ".join(valueColumnNames)
		self._sql += "%s WHERE " % tableName
		self._sql += "%s=? " % keyColumnNames[0]
		for keyColumnName in keyColumnNames[1:]:
			self._sql += "AND %s=? " % keyColumnName
		
	def __call__(self, k):
		c = self._db.cursor()
		if len(self._keyColumnNames) == 1:
			keyValues = (k,)
		else:
			keyValues = k
		c.execute(self._sql, keyValues)
		results = c.fetchall()
		if len(results) == 0:
			if self._raiseIfNotFound: raise Exception("No such key '%s' in %s" % (k, self._tableName))
			return self.NOTFOUND
		if len(results) > 1:
			raise Exception("Unexpected duplicate key")
		mappedResults = results[0]
		if len(mappedResults) == 1: return mappedResults[0]
		return mappedResults
		
class OneToOneDbLookup(object):
	def __init__(self, db, tableName, keyColumnNames, valueColumnNames, raiseIfNotFound=False):
		self.IdToValue = DbKeyLookup(db, tableName, keyColumnNames, valueColumnNames, raiseIfNotFound)
		self.ValueToId = DbKeyLookup(db, tableName, valueColumnNames, keyColumnNames, raiseIfNotFound)

def DBAtomic(f):
	def wrapper(self, *args, **kargs):
		cp = self.setDbCheckpoint()
		with self.dbToLock():
			try:
				return f(self, *args, **kargs)
			except Exception as e:
				self.revertToCheckpoint(cp)
				raise e
	return wrapper

class Civ4UnitTypeManager(object):
	def __init__(self, unitDb):
		self._unitDb = unitDb
		with self._unitDb:
			self._unitDb.execute("CREATE TABLE IF NOT EXISTS unit_types (id integer PRIMARY KEY, name text, strength integer)")
			self._unitDb.execute("CREATE TABLE IF NOT EXISTS promotion_types (id integer PRIMARY KEY, name text)")
		self._unrollCommands = []
		self.UnitTypeLookup = OneToOneDbLookup(self._unitDb, "unit_types", ["id"], ["name"])
		self.PromotionTypeLookup = OneToOneDbLookup(self._unitDb, "promotion_types", ["id"], ["name"])
			
	def dbToLock(self):
		return self._unitDb
		
	def setDbCheckpoint(self):
		self._unrollCommands = []
		
	def revertToCheckpoint(self):
		for cmd in self._unrollCommands:
			cmd()
		
	@DBAtomic
	def createUnitType(self, unitTypeName, strength):
		c = self._unitDb.cursor()
		c.execute("SELECT * FROM unit_types WHERE name=?", (unitTypeName,))
		if c.fetchone() != None:
			raise Exception("Duplicate Unit Type")
		self._unitDb.execute("INSERT into unit_types (name, strength) VALUES ('%s', %d)" % (unitTypeName, strength))
		
	@DBAtomic
	def editUnitType(self, unitTypeName, strength):
		c = self._unitDb.cursor()
		c.execute("SELECT * FROM unit_types WHERE name='%s'" % unitTypeName)
		if c.fetchone() == None:
			# Edit creates the unit type if it doesn't exist
			self._unitDb.execute("INSERT into unit_types (name, strength) VALUES ('%s', %d)" % (unitTypeName, strength))
		else:
			self._unitDb.execute("UPDATE unit_types SET strength=%d WHERE name='%s'" % (strength, unitTypeName))
	
	@DBAtomic
	def removeUnitType(self, unitTypeName):
		self._unitDb.execute("DELETE from unit_types WHERE name='%s'" % unitTypeName)
			
	def getUnitTypes(self, unitTypeName=None, unitTypeId=None):
		sqlCommand = "SELECT * FROM unit_types"
		if unitTypeName: sqlCommand += " WHERE name='%s'" % unitTypeName
		if unitTypeId: sqlCommand += " WHERE id=%d" % unitTypeId
		c = self._unitDb.cursor()
		c.execute(sqlCommand)
		return c.fetchall()
	
	@DBAtomic
	def addPromotionType(self, promotionName):
		c = self._unitDb.cursor()
		c.execute("SELECT * FROM promotion_types WHERE name=?", (promotionName,))
		if c.fetchone() == None:
			self._unitDb.execute("INSERT into promotion_types (name) VALUES (?)", (promotionName,))
	
	@DBAtomic
	def removePromotionType(self, promotionName):
		self._unitDb.execute("DELETE from promotion_types WHERE name='%s'" % (promotionName,))
			
	def getPromotionTypes(self, promotionName=None, promotionTypeId=None):
		sqlCommand = "SELECT * FROM promotion_types"
		params = []
		if promotionName: 
			sqlCommand += " WHERE name=?"
			params.append(promotionName)
		if promotionTypeId: 
			sqlCommand += " WHERE id=?"
			params.append(promotionTypeId)
		c = self._unitDb.cursor()
		c.execute(sqlCommand, params)
		return c.fetchall()
		
	def cloneTo(self, db):
		with db:
			db.execute("DROP TABLE IF EXISTS unit_types")
			db.execute("DROP TABLE IF EXISTS promotion_types")
			db.execute("CREATE TABLE unit_types (id integer PRIMARY KEY, name text, strength integer)")
			db.execute("CREATE TABLE promotion_types (id integer PRIMARY KEY, name text)")
			
			c_old = self._unitDb.cursor()
			c_old.execute("SELECT * FROM unit_types")
			for unitTypeData in c_old.fetchall():
				db.execute("INSERT INTO unit_types VALUES (?, ?, ?)", unitTypeData)
			c_old.execute("SELECT * FROM promotion_types")
			for promotionData in c_old.fetchall():
				db.execute("INSERT INTO promotion_types VALUES (?, ?)", promotionData)
		

class Civ4TroopManager(object):
	COMPOSITE_UNIT_TYPE = "Composite Unit"
	COMPOSITE_UNIT_TYPE_ID = -1
	
	EVENT_TYPES = [
	"create",
	"rename",
	"upgrade",
	"assign",
	"promote",
	"move",
	"transferhq",
	"destroy",
	"history",
	"victory"
	]
	
	class UnitDataView(object):
		def __init__(self):
			self.name = ""
			self.id = 0
			self.unitType = ""
			self.HQ = ""
			self.location = ""
			self.compositeUnitId = None
			self.isDead = False
			self.destroyedBy = None
			self.promotions = []
			self.history = []
			self.subordinateUnits = []
			self.victories = []
	
	def __init__(self, gameDb):
		self._unitManager = Civ4UnitTypeManager(gameDb)
		
		self._gameDb = gameDb
		c = self._gameDb.cursor()
		self._curTransaction = None
		
		# Unit Creation Table
		#  unit_id integer, year_created integer, type_id integer, string location_created
		#
		# Unit Event Table
		#  1 - year, unit_id, created(initial_type, initial_location)
		#  2 - year, unit_id, rename(name)
		#  3 - year, unit_id, upgrade(type_id)
		#  4 - year, unit_id, assign(superior_unit_id)
		#  5 - year, unit_id, promote(promotion_id)
		#  6 - year, unit_id, move(location)
		#  7 - year, unit_id, transferHQ(location)
		#  8 - year, unit_id, destroyed(defeatedByUnit)
		#  9 - year, unit_id, history(note)
		# 10 - year, unit_id, victory(unit_type)
		c.execute('''CREATE TABLE IF NOT EXISTS unit_events
			(event_id integer PRIMARY KEY, unit_id integer, year integer, event_type integer, event_data_id integer)''')
		
		c.execute('''CREATE TABLE IF NOT EXISTS creations 
		(creation_id integer PRIMARY KEY, initial_type_id integer, initial_location_id integer)''')
		c.execute('''CREATE TABLE IF NOT EXISTS names (name_id integer PRIMARY KEY, name text)''')
		c.execute('''CREATE TABLE IF NOT EXISTS locations (location_id integer PRIMARY KEY, location text)''')
		c.execute('''CREATE TABLE IF NOT EXISTS notes (note_id integer PRIMARY KEY, note text)''')
		c.execute('''CREATE TABLE IF NOT EXISTS enemy_units (unit_id integer PRIMARY KEY, type_id integer, owner_id integer, name_id integer)''')
		
		self._creationLookup = OneToOneDbLookup(self._gameDb, "creations", ["creation_id"], ["initial_type_id", "initial_location_id"])
		self._nameLookup = OneToOneDbLookup(self._gameDb, "names", ["name_id"], ["name"])
		self._locationLookup = OneToOneDbLookup(self._gameDb, "locations", ["location_id"], ["location"])
		self._noteLookup = OneToOneDbLookup(self._gameDb, "notes", ["note_id"], ["note"])
		self._enemyUnitLookup = OneToOneDbLookup(self._gameDb, "enemy_units", ["unit_id"], ["type_id", "owner_id", "name_id"])
		
		self._unitViewCache = {}
		self._unrollCommands = None
		
	def dbToLock(self):
		return self._gameDb
		
	def setDbCheckpoint(self):
		if self._unrollCommands == None:
			self._unrollCommands = []
		return len(self._unrollCommands)
		
	def revertToCheckpoint(self, checkPoint):
		if self._unrollCommands == None:
			# This might happen if some other revert reverted all the way to the beginning
			return
		while len(self._unrollCommands) > checkPoint:
			cmd = self._unrollCommands.pop(-1)
			cmd()
		if checkPoint == 0:
			self._unrollCommands = None
		
	def getUnitTypeManager(self):
		return self._unitManager
		
	def _unrollCommand(self, sql, args):
		self._gameDb.execute(sql, args)
		self._gameDb.commit()
		
	def _saveUnrollSingleEventCommand(self):
		if self._unrollCommands == None: return
		c = self._gameDb.cursor()
		c.execute("SELECT last_insert_rowid()")
		eventId, = c.fetchone()
		
		self._unrollCommands.append(lambda: self._unrollCommand("DELETE FROM unit_events WHERE event_id=?", (eventId,)))
		
	def _saveUnrollAllEventsCommand(self, unitId):
		if self._unrollCommands == None: return

		self._unrollCommands.append(lambda: self._unrollCommand("DELETE FROM unit_events WHERE unit_id=?", (unitId,)))
		self._unrollCommands.append(lambda: self._unrollCommand("DELETE FROM unit_events WHERE event_type=? AND event_data_id=?",
									(self.EVENT_TYPES.index('assign'), unitId)))
		
	def _raiseIfNull(self, *nonNullArgs):
		for arg in nonNullArgs:
			if arg == None: 
				raise Exception("Unacceptable 'null' argument")
			elif arg == DbKeyLookup.NOTFOUND:
				raise Exception("Argument not found")
				
	def _raiseIfInvalidYear(self, unitId, year):
		yearCreated, yearDestroyed = self.getUnitLifespan(unitId)
		if yearCreated == None:
			raise Exception("No such unit with ID %d" % unitId)
		if year < yearCreated:
			raise Exception("Cannot insert an event in year %d before it was created in year %d" % (year, yearCreated))
		if yearDestroyed != None and year > yearDestroyed:
			raise Exception("Cannot insert an event in year %d after it was destroyed in year %d" % (year, yearDestroyed))
			
	def _invalidateCache(self, unitId):
		if unitId in self._unitViewCache.keys():
			del self._unitViewCache[unitId]
			
	def _unitTypeToId(self, unitType):
		if unitType == self.COMPOSITE_UNIT_TYPE:
			return self.COMPOSITE_UNIT_TYPE_ID
		return self._unitManager.UnitTypeLookup.ValueToId(unitType)
		
	def _unitIdToType(self, unitTypeId):
		if unitTypeId == self.COMPOSITE_UNIT_TYPE_ID:
			return self.COMPOSITE_UNIT_TYPE
		return self._unitManager.UnitTypeLookup.IdToValue(unitTypeId)
				
	def getUnitLifespan(self, unitId):
		c = self._gameDb.cursor()
		c.execute('''SELECT (year) FROM unit_events WHERE event_type=? AND unit_id=?''', 
				(self.EVENT_TYPES.index('create'),
				unitId))
		results = c.fetchall()
		if len(results) == 0:
			return None, None
		yearCreated, = results[0]
		
		c.execute('''SELECT (year) FROM unit_events WHERE event_type=? AND unit_id=?''',
				(self.EVENT_TYPES.index('destroy'),
				unitId))
		results = c.fetchall()
		if len(results) == 0:
			return yearCreated, None
		yearDestroyed, = results[0]
		return yearCreated, yearDestroyed
	
	@DBAtomic
	def createUnit(self, year, unitType, location):
		c = self._gameDb.cursor()
		
		unitTypeId = self._unitTypeToId(unitType)
		self._raiseIfNull(unitTypeId)
		
		locationId = self._locationLookup.ValueToId(location)
		if locationId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into locations (location) VALUES (?)", (location,))
			locationId = self._locationLookup.ValueToId(location)
			
		creationId = self._creationLookup.ValueToId((unitTypeId, locationId))
		if creationId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into creations (initial_type_id, initial_location_id) VALUES (?, ?)", (unitTypeId, locationId))
			creationId = self._creationLookup.ValueToId((unitTypeId, locationId))

		
		c.execute("SELECT MAX(unit_id) FROM unit_events")
		lastUnitId = c.fetchone()[0]
		if not lastUnitId:
			lastUnitId = 0
		newUnitId = lastUnitId + 1
		
		# TODO: maybe consider block multiple year-location combinations
			
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(newUnitId, year, self.EVENT_TYPES.index("create"), creationId))
							
		self._saveUnrollAllEventsCommand(newUnitId)
		return newUnitId
		
	@DBAtomic
	def renameUnit(self, unitId, year, newName):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		nameId = self._nameLookup.ValueToId(newName)
		if nameId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into names (name) VALUES (?)", (newName,))
			nameId = self._nameLookup.ValueToId(newName)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("rename"), nameId))
							
		self._saveUnrollSingleEventCommand()

	@DBAtomic
	def upgradeUnit(self, unitId, year, newUnitType):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		newUnitTypeId = self._unitTypeToId(newUnitType)
		self._raiseIfNull(newUnitTypeId)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("upgrade"), newUnitTypeId))
		self._saveUnrollSingleEventCommand()
							
	@DBAtomic
	def assignUnitToComposite(self, unitId, year, compositeUnitId):
		self._invalidateCache(unitId)
		self._invalidateCache(compositeUnitId)
		self._raiseIfInvalidYear(unitId, year)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("assign"), compositeUnitId))
							
		self._saveUnrollSingleEventCommand()
							
	@DBAtomic
	def promoteUnit(self, unitId, year, promotionType):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		c = self._gameDb.cursor()
		c.execute('''SELECT (event_data_id) FROM unit_events WHERE unit_id=? AND event_type=?''',
				(unitId, self.EVENT_TYPES.index('create')))
		createId = c.fetchone()[0]
		createdTypeId, createdLocationId = self._creationLookup.IdToValue(createId)
		
		if createdTypeId == self.COMPOSITE_UNIT_TYPE_ID:
			raise Exception("Cannot promote composite units")
		
		promotionTypeId = self._unitManager.PromotionTypeLookup.ValueToId(promotionType)
		self._raiseIfNull(promotionTypeId)
		
		c.execute('''SELECT (event_data_id) FROM unit_events WHERE unit_id=? AND event_type=?''',
				(unitId, self.EVENT_TYPES.index('promote')))
		for extentPromotionTypeId, in c.fetchall():
			if extentPromotionTypeId == promotionTypeId:
				raise Exception("Duplicate promotion")
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("promote"), promotionTypeId))
							
		self._saveUnrollSingleEventCommand()
							
	@DBAtomic
	def moveUnit(self, unitId, year, newLocation):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		locationId = self._locationLookup.ValueToId(newLocation)
		if locationId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into locations (location) VALUES (?)", (newLocation,))
			locationId = self._locationLookup.ValueToId(newLocation)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("move"), locationId))
		
		self._saveUnrollSingleEventCommand()
							
	@DBAtomic
	def transferUnitHq(self, unitId, year, newLocation):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		locationId = self._locationLookup.ValueToId(newLocation)
		if locationId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into locations (location) VALUES (?)", (location,))
			locationId = self._locationLookup.ValueToId(location)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("transferhq"), locationId))
		self._saveUnrollSingleEventCommand()
		
	def _enemyUnitToId(self, enemyUnitType, enemyUnitOwner, enemyUnitName=None):
		enemyUnitTypeId = self._unitTypeToId(enemyUnitType)
		self._raiseIfNull(enemyUnitTypeId)
		
		enemyUnitOwnerId = self._nameLookup.ValueToId(enemyUnitOwner)
		if enemyUnitOwnerId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute('INSERT into names (name) VALUES (?)', (enemyUnitOwner,))
			enemyUnitOwnerId = self._nameLookup.ValueToId(enemyUnitOwner)
			
		if not enemyUnitName:
			enemyUnitName = "" # Translate None to ""
			
		# it's annoying to create something for "", but it's not that big of a deal
		enemyUnitNameId = self._nameLookup.ValueToId(enemyUnitName)
		if enemyUnitNameId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute('INSERT into names (name) VALUES (?)', (enemyUnitName,))
			enemyUnitNameId = self._nameLookup.ValueToId(enemyUnitName)
			
		enemyUnitId = self._enemyUnitLookup.ValueToId((enemyUnitTypeId, enemyUnitOwnerId, enemyUnitNameId))
		if enemyUnitId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute('INSERT into enemy_units (type_id, owner_id, name_id) VALUES (?, ?, ?)', (enemyUnitTypeId,
																											enemyUnitOwnerId,
																											enemyUnitNameId))
			enemyUnitId = self._enemyUnitLookup.ValueToId((enemyUnitTypeId, enemyUnitOwnerId, enemyUnitNameId))
		return enemyUnitId
		
	def _enemyUnitIdToValues(self, enemyUnitId):
		enemyUnitTypeId, enemyUnitOwnerId, enemyUnitNameId = self._enemyUnitLookup.IdToValue(enemyUnitId)
		enemyUnitType = self._unitIdToType(enemyUnitTypeId)
		enemyUnitOwner = self._nameLookup.IdToValue(enemyUnitOwnerId)
		enemyUnitName = self._nameLookup.IdToValue(enemyUnitNameId)
		return (enemyUnitType, enemyUnitOwner, enemyUnitName)
		
		
	@DBAtomic
	def destroyUnit(self, unitId, year, enemyUnitType=None, enemyUnitOwner=None, enemyUnitName=None):
		self._invalidateCache(unitId)
		#createdTypeId, createdLocationId = self._creationLookup.IdToValue(createId)
		
		yearCreated, yearDestroyed = self.getUnitLifespan(unitId)
		
		if yearDestroyed != None:
			raise Exception("Unit already destroyed.")
			
		c = self._gameDb.cursor()
		c.execute('''SELECT year FROM unit_events WHERE unit_id=? AND year>?''',(unitId, year))
		yearResults = c.fetchall()
		if len(yearResults) > 0:
			raise Exception("Cannot destroy unit in a year before other events")
		
		if enemyUnitType != None:
			if enemyUnitOwner == None:
				raise Exception("If an enemy unit type is specified, an onwer must be specified as well.")
			defeatedByUnitTypeId = self._enemyUnitToId(enemyUnitType, enemyUnitOwner, enemyUnitName)
		else:
			defeatedByUnitTypeId = None
			
		unitView = self.getUnitView(unitId)
		if unitView.compositeUnitId != None:
			self._invalidateCache(unitView.compositeUnitId)
		for subUnitId in unitView.subordinateUnits:
			self.assignUnitToComposite(subUnitId, year, None)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("destroy"), defeatedByUnitTypeId))
		self._saveUnrollSingleEventCommand()
							
	@DBAtomic
	def unitHistory(self, unitId, year, note):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		noteId = self._noteLookup.ValueToId(note)
		if noteId == DbKeyLookup.NOTFOUND:
			self._gameDb.execute("INSERT into notes (note) VALUES (?)", (note,))
			noteId = self._noteLookup.ValueToId(note)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("history"), noteId))
		self._saveUnrollSingleEventCommand()
		
	@DBAtomic
	def unitVictory(self, unitId, year, enemyUnitType, enemyUnitOwner, enemyUnitName=None):
		self._invalidateCache(unitId)
		self._raiseIfInvalidYear(unitId, year)
		
		enemyUnitId = self._enemyUnitToId(enemyUnitType, enemyUnitOwner, enemyUnitName)
		
		self._gameDb.execute("INSERT into unit_events (unit_id, year, event_type, event_data_id) VALUES (?, ?, ?, ?)", 
							(unitId, year, self.EVENT_TYPES.index("victory"), enemyUnitId))
		
	@DBAtomic
	def deleteEvent(self, eventId):
		c = self._gameDb.cursor()
		c.execute('SELECT * FROM unit_events WHERE event_id=?', (eventId,))
		eventId, unitId, year, eventType, eventDataId = c.fetchone()
		if eventType == self.EVENT_TYPES.index('create'):
			# For create events, we have to delete everything
			self._gameDb.execute('DELETE FROM unit_events WHERE unit_id=?', (unitId,))
		else:
			# all other event types, just delete the event
			self._gameDb.execute("DELETE FROM unit_events WHERE event_id=?", (eventId,))
		# assume that deleting the event screws up the cache
		self._unitViewCache = {}
		
	def getMinMaxYears(self):
		c = self._gameDb.cursor()
		c.execute("SELECT MIN(year), MAX(year) FROM unit_events")
		results = c.fetchall()
		if not results: return None, None
		else: return results[0]
	
	def getUnitList(self, year=None):
		c = self._gameDb.cursor()
		sqlCommand = "SELECT * FROM unit_events WHERE event_type=?"
		params = [self.EVENT_TYPES.index('create')]
		if year != None:
			sqlCommand += " AND year<=?"
			params.append(year)
		c.execute(sqlCommand, params)
		sqlResults = c.fetchall()
		# get just the Ids
		return map(lambda sqlTuple: sqlTuple[1], sqlResults)
		
	def getEventsList(self, unitId):
		c = self._gameDb.cursor()
		c.execute('SELECT * FROM unit_events WHERE unit_id=?', (unitId,))
		return c.fetchall()
		
	def _assignedCompositeUnit(self, unitId, year=None):
		yearCreated, yearDestroyed = self.getUnitLifespan(unitId)
		if yearDestroyed != None:
			return None
			
		c = self._gameDb.cursor()
		if year == None:
			c.execute("SELECT event_data_id FROM unit_events WHERE unit_id=? AND event_type=?", 
				(unitId, self.EVENT_TYPES.index('assign')))
		else:
			c.execute("SELECT event_data_id FROM unit_events WHERE unit_id=? AND event_type=? AND year<=?", 
				(unitId, self.EVENT_TYPES.index('assign'), year))
		assignResults = c.fetchall()
		if len(assignResults) == 0: return None
		lastAssigned, = assignResults[-1]
		return lastAssigned
		
	def getUnitView(self, unitId, year=None):
		if unitId in self._unitViewCache.keys():
			cacheYear, cacheView = self._unitViewCache[unitId]
			# Assume that later than cache year is up-to-date
			# invalidateCache is supposed to get rid of this after a change
			if year == None or year >= cacheYear:
				return cacheView
		else:
			cacheYear = None
		
		c = self._gameDb.cursor()
		if year == None:
			c.execute("SELECT * FROM unit_events WHERE unit_id=?", (unitId,))
		else:
			c.execute("SELECT * FROM unit_events WHERE unit_id=? AND year<=?", (unitId,year))
		unitEvents = c.fetchall()
		if len(unitEvents) == 0:
			return None

		unitView = self.UnitDataView()
		unitView.id = unitId
		
		# If year == none, lastEventYear will get set by eventYear below
		# if year is not none, it should be >= the last event year
		lastEventYear = year
		
		for e in unitEvents:
			eventId, unitId, eventYear, eventTypeId, eventDataId = e
			if lastEventYear == None or eventYear > lastEventYear:
				lastEventYear = eventYear
			eventType = self.EVENT_TYPES[eventTypeId]
			
			if eventType == "create":
				initialTypeId, initialLocationId = self._creationLookup.IdToValue(eventDataId)
				initialType = self._unitIdToType(initialTypeId)
				initialLocation = self._locationLookup.IdToValue(initialLocationId)
				unitView.unitType = initialType
				unitView.location = initialLocation
				if initialType == self.COMPOSITE_UNIT_TYPE:
					unitView.HQ = initialLocation
				unitView.name = "%s-%d" % (initialType, unitId)
				unitView.history.append((eventId, eventYear, "%s created in %s" % (initialType, initialLocation)))
			elif eventType == "rename":
				name = self._nameLookup.IdToValue(eventDataId)
				unitView.name = name
				unitView.history.append((eventId, eventYear, "renamed '%s'" % name))
			elif eventType == "upgrade":
				unitType = self._unitIdToType(eventDataId)
				unitView.unitType = unitType
				unitView.history.append((eventId, eventYear, "upgraded to '%s'" % unitType))
			elif eventType == "assign":
				unitView.compositeUnitId = eventDataId
				if unitView.compositeUnitId != None:
					compositeUnitView = self.getUnitView(unitView.compositeUnitId, year)
					unitView.history.append((eventId, eventYear, "assigned to '%s'" % compositeUnitView.name))
				else:
					unitView.history.append((eventId, eventYear, "assigned independent"))
			elif eventType == "promote":
				promotionType = self._unitManager.PromotionTypeLookup.IdToValue(eventDataId)
				unitView.promotions.append(promotionType)
				unitView.history.append((eventId, eventYear, "promoted to '%s'" % promotionType))
			elif eventType == "move":
				location = self._locationLookup.IdToValue(eventDataId)
				unitView.location = location
				unitView.history.append((eventId, eventYear, "location changed to '%s'" % location))
			elif eventType == "transferhq":
				location = self._locationLookup.IdToValue(eventDataId)
				unitView.HQ = location
				unitView.history.append((eventId, eventYear, "headquarters transferred to '%s'" % location))
			elif eventType == "destroy":
				unitView.isDead = True
				if eventDataId != None:
					enemyUnitType, enemyUnitOwner, enemyUnitName = self._enemyUnitIdToValues(eventDataId)
					unitView.destroyedBy = (enemyUnitType, enemyUnitOwner, enemyUnitName)
					if enemyUnitName:
						historyNote = "destroyed by %s's %s (%s)" % (enemyUnitOwner, enemyUnitName, enemyUnitType)
					else:
						historyNote = "destroyed by %s's %s unit" % (enemyUnitOwner, enemyUnitType)
				else:
					historyNote = "destroyed/disbanded"
				unitView.history.append((eventId, eventYear, historyNote))
			elif eventType == "history":
				note = self._noteLookup.IdToValue(eventDataId)
				unitView.history.append((eventId, eventYear, note))
			elif eventType == "victory":
				enemyUnitType, enemyUnitOwner, enemyUnitName = self._enemyUnitIdToValues(eventDataId)
				unitView.victories.append((eventYear, enemyUnitType, enemyUnitOwner, enemyUnitName))
				if enemyUnitName:
					unitView.history.append((eventId, eventYear, "destroyed %s's %s (%s)" % (enemyUnitOwner, enemyUnitName, enemyUnitType)))
				else:
					unitView.history.append((eventId, eventYear, "destroyed %s's %s unit" % (enemyUnitOwner, enemyUnitType)))
			else:
				raise Exception("No such event '%s'" % eventType)
		
		if unitView.unitType == self.COMPOSITE_UNIT_TYPE:
			if year == None:
				c.execute("SELECT unit_id FROM unit_events WHERE event_type=? AND event_data_id=?", 
					(self.EVENT_TYPES.index('assign'), unitId))
			else:
				c.execute("SELECT unit_id FROM unit_events WHERE event_type=? AND event_data_id=? AND year<=?", 
					(self.EVENT_TYPES.index('assign'), unitId, year))
			assignEvents = c.fetchall()
			for assignEvent in assignEvents:
				# these are all units *ever* assigned to this unit. See which ones still are assigned.
				subUnitId, = assignEvent
				if subUnitId in unitView.subordinateUnits: continue
				lastAssignment = self._assignedCompositeUnit(subUnitId, year)
				if lastAssignment == unitId:
					# as of 'year' (or latest), still assigned to me
					unitView.subordinateUnits.append(subUnitId)
				
		# Sort on date only.
		unitView.history.sort(key=lambda historyItem: historyItem[0])
		if cacheYear == None or lastEventYear >= cacheYear:
			# This should prevent getting an older version of the unit
			# stuck in the cache.
			self._unitViewCache[unitView.id] = (lastEventYear, unitView)
		return unitView		
			
if __name__=="__main__":
	gameDb = sqlite3.connect(":memory:")
	typeManager = Civ4UnitTypeManager(gameDb)
	typeManager.editUnitType("Warrior", 2)
	typeManager.editUnitType("Axeman", 5)
	typeManager.editUnitType("Archer", 3)
	typeManager.addPromotionType("Combat I")
	typeManager.addPromotionType("City Raider I")
	print(typeManager.getUnitTypes())
	print(typeManager.getPromotionTypes())
	
	#gameDb = sqlite3.connect(":memory:")
	
	troopManager = Civ4TroopManager(gameDb)
	printTemplate = """
Name: %(name)s
Type: %(type)s
composite: %(composite)s
subordinates: %(subordinates)s
history: %(history)s
"""
	def printView(v):
		d = {}
		d["name"] = v.name
		d["type"] = v.unitType
		compositeUnitId = v.compositeUnitId
		d["composite"] = compositeUnitId == None and "<NONE>" or troopManager.getUnitView(compositeUnitId).name
		d["subordinates"] = "\n\t".join(v.subordinateUnits)
		d["history"] = ""
		for date, msg in v.history:
			d["history"] += "\n\t%d: %s" % (date, msg)
		print(printTemplate % d)
	
	unit1 = troopManager.createUnit(-4000, "Warrior", "Paris")
	troopManager.renameUnit(unit1, -4000, "King's Guard")
	unit2 = troopManager.createUnit(-3900, "Archer", "Paris")
	troopManager.renameUnit(unit2, -3900, "King's Archers")

	cUnit1 = troopManager.createUnit(-4000, troopManager.COMPOSITE_UNIT_TYPE, "Paris")
	troopManager.renameUnit(cUnit1, -4000, "King's Men")
	
	print("First info\n")
	
	printView(troopManager.getUnitView(unit1))
	printView(troopManager.getUnitView(unit2))
	printView(troopManager.getUnitView(cUnit1))
	
	troopManager.assignUnitToComposite(unit1, -4000, cUnit1)
	troopManager.assignUnitToComposite(unit2, -3900, cUnit1)
	troopManager.upgradeUnit(unit1, -3000, "Axeman")
	troopManager.moveUnit(unit1, -2500, "Spanish Campaign")
	troopManager.promoteUnit(unit1, -2450, "City Raider I")
	troopManager.destroyUnit(unit1, -2400)
	troopManager.unitHistory(unit1, -2400, "Destroyed assaulting Madrid")
	
	print("Second info\n")
	
	printView(troopManager.getUnitView(unit1))
	printView(troopManager.getUnitView(unit2))
	printView(troopManager.getUnitView(cUnit1))
	
	print("Third info as of year 3500BC")
	
	printView(troopManager.getUnitView(unit1, -3500))
	printView(troopManager.getUnitView(unit2, -3500))
	printView(troopManager.getUnitView(cUnit1, -3500))
	
	newUnitDb = sqlite3.connect(":memory:")
	troopManager.getUnitTypeManager().cloneTo(newUnitDb)
	
	print("Year range %d-%d\n" % troopManager.getMinMaxYears())