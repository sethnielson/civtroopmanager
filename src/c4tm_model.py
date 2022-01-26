#!/usr/bin/python
import sqlite3, json
        

class CivTroopManager(object):
    COMPOSITE_UNIT_TYPE = "_Composite_Unit_"
    
    EVENT_TYPES = [
    "create",
    "rename",
    "upgrade",
    "assign",
    "assign_to",
    "unassign",
    "promote",
    "move",
    "transferhq",
    "destroy",
    "history",
    "victory"
    ]
    
    class EventView:
        @classmethod
        def sort_by_date_key(cls, event_view):
            return event_view.year, event_view.event_id
            
        def __init__(self, event_id, unit_id, year, event_type_id, event_json):
            self.event_id = event_id
            self.unit_id = unit_id
            self.year = year
            self.type_id = event_type_id
            self.event_type = CivTroopManager.EVENT_TYPES[event_type_id]
            self.event_json = event_json
            self.event_data = json.loads(event_json)
            
    
    class UnitDataView(object):
        def __init__(self):
            self.name = ""
            self.id = 0
            self.unit_type = ""
            self.HQ = ""
            self.location = ""
            self.composite_unit_id = None
            self.is_dead = False
            self.destroyed_by = None
            self.promotions = []
            self.history = []
            self.subordinate_units = []
            self.victories = []
            self.display_key = lambda f, v: v
            self.display = CivTroopManager.UnitDataDisplayView(self)
            
    class UnitDataDisplayView:
        def __init__(self, unit_view):
            self._unit_view = unit_view
            
        def __getattribute__(self, attr):
            if attr.startswith("_") or attr.startswith("display"): return super().__getattribute__(attr)
            return self._unit_view.display_key(attr, getattr(self._unit_view, attr))
    
    def __init__(self, gameDb):
        self._gameDb = gameDb
        c = self._gameDb.cursor()
        self._curTransaction = None
        
        # Unit Events
        #  event_id, unit_id, year, event_type_id, event_json
        #  event_id is really only needed for deletion
        #  Sorting within the same year is order of entry
        #  json converted to dictionary in view
        c.execute('''CREATE TABLE IF NOT EXISTS unit_events
            (event_id integer PRIMARY KEY, unit_id integer, year integer, event_type_id integer, event_json text)''')
        
        self._unit_view_cache = {}
        
    def commit(self):
        self._gameDb.commit()
        
    def undo(self):
        self._gameDb.rollback()
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
            return True
        else:
            self.undo()
            return False
        
    def _insert_unit_event(self, unit_id, year, event_type, **event_data):
        event_json = json.dumps(event_data)
        query = "INSERT into unit_events (unit_id, year, event_type_id, event_json) VALUES (?, ?, ?, ?)"
        self._gameDb.execute(query,(unit_id, year, self.EVENT_TYPES.index(event_type), event_json))
                        
    def _get_unit_ids(self, min_year=None, max_year=None, event_types = None):
        unit_ids = []
        c = self._gameDb.cursor()
        if not event_types:
            event_types = [None]
        for event_type in event_types:
            query = "SELECT DISTINCT (unit_id) FROM unit_events"
            conditionals = []
            params = []
            
            if event_type is not None:
                event_type_id = self.EVENT_TYPES.index(event_type)
                conditionals.append("event_type_id=?")
                params.append(event_type_id)
            if min_year is not None:
                conditionals.append("year>=?")
                params.append(min_year)
            if max_year is not None:
                conditionals.append("year<=?")
                params.append(max_year)
            if conditionals:
                query += " WHERE " + " AND ".join(conditionals)
            c.execute(query, tuple(params))
            results = c.fetchall()
            for result in results:
                unit_id, = result
                unit_ids.append(unit_id)
        return set(unit_ids)
    
    def _get_unit_events(self, unit_id, min_year=None, max_year=None, event_types=None):
        events = []
        c = self._gameDb.cursor()
        if not event_types:
            event_types = [None]
        for event_type in event_types:
            query = "SELECT * FROM unit_events WHERE unit_id=?"
            params = [unit_id]
            
            if event_type is not None:
                query += " AND event_type_id=?"
                event_type_id = self.EVENT_TYPES.index(event_type)
                params.append(event_type_id)
            if min_year is not None:
                query += " AND year>=? "
                params.append(min_year)
            if max_year is not None:
                query += " AND year<=?"
                params.append(max_year)
            c.execute(query, tuple(params))
            results = c.fetchall()
            for result in results:
                events.append(self.EventView(*result))
        events.sort(key=self.EventView.sort_by_date_key) # return sorted by year
        return events
        
    def is_unit_composite(self, unit_id):
        create_events = self._get_unit_events(unit_id, event_types=["create"])
        create_event = create_events[0]
        return create_event.event_data["unit_type"] == self.COMPOSITE_UNIT_TYPE
                
    def _raise_if_invalid_year(self, unit_id, year):
        yearCreated, yearDestroyed = self.get_unit_lifespan(unit_id)
        if yearCreated == None:
            raise Exception("No such unit with ID %d" % unit_id)
        if year < yearCreated:
            raise Exception("Cannot insert an event in year %d before it was created in year %d" % (year, yearCreated))
        if yearDestroyed != None and year > yearDestroyed:
            raise Exception("Cannot insert an event in year %d after it was destroyed in year %d" % (year, yearDestroyed))
            
    def _invalidate_cache(self, unit_id):
        if unit_id in self._unit_view_cache.keys():
            del self._unit_view_cache[unit_id]
                
    def get_unit_lifespan(self, unit_id):
        lifespan_events = self._get_unit_events(unit_id, event_types=["create", "destroy"])
        if len(lifespan_events) < 1:
            return None, None
        if len(lifespan_events) > 2:
            raise Exception("Should be 1 create event, 1 destroy event. Got {}".format(len(lifespan_events)))
        
        create_event = lifespan_events[0]
        if create_event.event_type != "create":
            raise Exception("The first event should be create but got {}. Internal Error".format(unit_id))
        create_year = create_event.year
        
        if len(lifespan_events) == 2:
            destroy_year = lifespan_events[1].year
        else:
            destroy_year = None
        
        return create_year, destroy_year
        
    """def create_composite_unit(self, year, name, location):
        self._create_unit(year, name, self.COMPOSITE_UNIT_TYPE, location)
    
    def create_civ_unit(self, year, name, unit_type, location):
        if unit_type == self.COMPOSITE_UNIT_TYPE:
            raise Exception("Unit type cannot be {}. Reserved.".format(self.COMPOSITE_UNIT_TYPE))
        self._create_unit(year, name, unit_type, location)"""
    
    def create_unit(self, year, name, unit_type, location):
        c = self._gameDb.cursor()
        
        c.execute("SELECT MAX(unit_id) FROM unit_events")
        last_unit_id = c.fetchone()[0]
        if not last_unit_id:
            last_unit_id = 0
        new_unit_id = last_unit_id + 1
        
        self._insert_unit_event(new_unit_id, year, "create", name=name, unit_type=unit_type, location=location)
        return new_unit_id
        
    def rename_unit(self, unit_id, year, new_name):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        self._insert_unit_event(unit_id, year, "rename", name=new_name)

    def upgrade_unit(self, unit_id, year, new_unit_type):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "upgrade", unit_type=new_unit_type)
                            
    def assign_unit_to_composite(self, unit_id, year, composite_unit_id):
        if not self.is_unit_composite(composite_unit_id):
            raise Exception("Cannot assign a unit to a unit that is not a composite.")
            
        self._invalidate_cache(unit_id)
        self._invalidate_cache(composite_unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "assign", composite_unit_id="composite_unit_id")
        self._insert_unit_event(composite_unit_id, year, "assign_to", unit_id=unit_id)
        
    def unassign_unit_to_composite(self, unit_id, year):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "unassign")
                            
    def promote_unit(self, unit_id, year, promotion):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        if self.is_unit_composite(unit_id):
            raise Exception("Cannot promote a unit that is a composite.")
            
        self._insert_unit_event(unit_id, year, "promote", promotion=promotion)
                            
    def move_unit(self, unit_id, year, new_location):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "move", location=new_location)
                            
    def transfer_unit_hq(self, unit_id, year, new_location):
        #if not self.is_unit_composite(unit_id):
        #    raise Exception("Cannot assign an HQ location to a unit that is not a composite.")
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "transferhq", location=new_location)
        
    def destroy_unit(self, unit_id, year, enemy_unit_owner, enemy_unit_type):
        self._invalidate_cache(unit_id)
        yearCreated, yearDestroyed = self.get_unit_lifespan(unit_id)
        
        if yearDestroyed != None:
            raise Exception("Unit already destroyed.")
        
        self._insert_unit_event(unit_id, year, "destroy", enemy_unit_owner=enemy_unit_owner, enemy_unit_type=enemy_unit_type)
        
    def disband_unit(self, unit_id, year):
        self._invalidate_cache(unit_id)
        yearCreated, yearDestroyed = self.get_unit_lifespan(unit_id)
        
        if yearDestroyed != None:
            raise Exception("Unit already destroyed.")
        
        self._insert_unit_event(unit_id, year, "destroy", enemy_unit_owner=None, enemy_unit_type=None)
                            
    def unit_history(self, unit_id, year, note):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "history", note=note)
        
    def unit_victory(self, unit_id, year, enemy_unit_owner, enemy_unit_type):
        self._invalidate_cache(unit_id)
        self._raise_if_invalid_year(unit_id, year)
        
        self._insert_unit_event(unit_id, year, "victory", enemy_unit_owner=enemy_unit_owner, enemy_unit_type=enemy_unit_type)

    def delete_event(self, event_id):
        query = "SELECT * FROM unit_events WHERE event_id=?"
        c = self._gameDb.cursor()
        c.execute(query, (event_id,))
        result = c.fetchone()
        if not result:
            raise Exception("No such event id to delete")
        q = self.EventView(*result)
        to_delete = [q]
        if q.event_type == "create":
            # only permit delete create if all other events are deleted for this unit
            unit_events = self._get_unit_events(q.unit_id)
            if len(unit_events) != 1:
                raise Exception("Cannot delete a create event unless all other events deleted")
        elif q.event_type == "assign":
            query = "SELECT * FROM unit_events WHERE unit_id=? AND year=? AND event_type_id=?"
            params = (q.event_data["composite_unit_id"], q.year, self.EVENT_TYPES.index("assign_to"))
            c.execute(query, params)
            result = c.fetchone()
            if result is None:
                raise Exception("Database error. No matching 'assign_to'")
            to_delete.append(self.EventView(*result))
        elif q.event_type == "assign":
            query = "SELECT * FROM unit_events WHERE unit_id=? AND year=? AND event_type_id=?"
            params = (q.event_data["unit_id"], q.year, self.EVENT_TYPES.index("assign"))
            c.execute(query, params)
            result = c.fetchone()
            if result is None:
                raise Exception("Database error. No matching 'assign'")
            to_delete.append(self.Eventview(*result))
            
        for del_event in to_delete:
            self._invalidate_cache(del_event.unit_id)
            query = "DELETE FROM unit_events WHERE event_id=?"
            params = (del_event.event_id,)
            c.execute(query, params)
        
    def get_min_max_years(self):
        c = self._gameDb.cursor()
        c.execute("SELECT MIN(year), MAX(year) FROM unit_events")
        results = c.fetchall()
        if not results: return None, None
        else: return results[0]
    
    def get_unit_list(self, year=None, live_only=False):
        created = self._get_unit_ids(max_year=year)
        if live_only:
            destroyed = self._get_unit_ids(max_year=year, event_types=["destroy"])
            created = [UID for UID in created if UID not in destroyed] # too slow?
        return created
        
    def get_events_list(self, unit_id, year=None):
        return self._get_unit_events(unit_id, max_year=year)
        
        
    def get_unit_view(self, unit_id,year=None, display_key=None):
        if display_key is None:
            display_key = lambda field_name, field_key: field_key
            
        if unit_id in self._unit_view_cache.keys():
            cacheYear, cacheView = self._unit_view_cache[unit_id]
            # Assume that later than cache year is up-to-date
            # invalidateCache is supposed to get rid of this after a change
            if year == None or year >= cacheYear:
                cacheView.display_key = display_key
                return cacheView
        else:
            cacheYear = None
        
        unit_events = self._get_unit_events(unit_id, max_year=year)
        if len(unit_events) == 0:
            return None

        unit_view = self.UnitDataView()
        unit_view.display_key = display_key
        unit_view.id = unit_id
        
        if year == None:
            lastevent_year = unit_events[-1].year
        else:
            lastevent_year = year
            
        units_assigned = []
        
        for e in unit_events:
            event_id, event_year, event_type, event_data = e.event_id, e.year, e.event_type, e.event_data
            
            if event_type == "create":
                unit_view.name = event_data["name"]
                unit_view.unit_type = event_data["unit_type"]
                unit_view.location = event_data["location"]
                if unit_view.unit_type == self.COMPOSITE_UNIT_TYPE:
                    unit_view.HQ = unit_view.location
                unit_view.history.append((event_id, event_year, 
                    "%s (%s) created in %s" % (unit_view.display.name, unit_view.display.unit_type, unit_view.display.location)))
            elif event_type == "rename":
                unit_view.name = event_data["name"]
                unit_view.history.append((event_id, event_year, "renamed '%s'" % unit_view.display.name))
            elif event_type == "upgrade":
                unit_view.unit_type = event_data["unit_type"]
                unit_view.history.append((event_id, event_year, "upgraded to '%s'" % unit_view.display.unit_type))
            elif event_type == "assign":
                unit_view.composite_unit_id = event_data["composite_unit_id"]
                composite_unit_view = self.get_unit_view(unit_view.composite_unit_id, year, display_key)
                unit_view.history.append((event_id, event_year, "assigned to '%s'" % composite_unit_view.name))
            elif event_type == "assign_to":
                units_assigned.append(event_data["unit_id"])
            elif event_type == "unassign":
                unit_view.history.append((event_id, event_year, "released for independent action"))
            elif event_type == "promote":
                promotion = event_data["promotion"]
                unit_view.history.append((event_id, event_year, "promoted to '%s'" % unit_view.display.promotion))
            elif event_type == "move":
                unit_view.location = event_data["location"]
                unit_view.history.append((event_id, event_year, "location changed to '%s'" % unit_view.display.location))
            elif event_type == "transferhq":
                unit_view.HQ = event_data["location"]
                unit_view.history.append((event_id, event_year, "headquarters transferred to '%s'" % unit_view.display.HQ))
            elif event_type == "destroy":
                unit_view.is_dead = True
                if event_data["destroyed_by"] != None:
                    enemy_unit_owner, enemy_unit_type = event_data["destroyed_by"]
                    unit_view.destroyed_by = (enemy_unit_type, enemy_unit_owner)
                    historyNote = "destroyed by %s's %s unit" % (display_key("player",enemy_unit_owner), display_key("unit_type",enemy_unit_type))
                else:
                    historyNote = "disbanded peacefully"
                unit_view.history.append((event_id, event_year, historyNote))
            elif event_type == "history":
                unit_view.history.append((event_id, event_year, event_data["note"]))
            elif event_type == "victory":
                enemyunit_type, enemy_unit_owner = event_data["unit_destroyed"]
                unit_view.victories.append((event_year, enemy_unit_type, enemy_unit_owner))
                unit_view.history.append((event_id, event_year, "destroyed %s's %s unit" % (display_key("player",enemy_unit_owner), display_key("unit_type",enemy_unit_type))))
            else:
                raise Exception("No such event '%s'" % event_type)
        
        if unit_view.unit_type == self.COMPOSITE_UNIT_TYPE:
            for assigned_unit_id in units_assigned:
                # these are all units *ever* assigned to this unit. See which ones still are assigned.
                unit_events = self._get_unit_events(assigned_unit_id, max_year=year, event_types=["assign", "unassigned"])
                if len(unit_events) == 0:
                    # This should never happen
                    raise Exception("Should never happen. Was assigned to, but has not assign events")
                last_assign_year, last_assign_event, last_assign_data = unit_events[-1]
                if last_assign_event == "assign":
                    composite_unit_id = last_assign_data["composite_unit_id"]
                else:
                    composite_unit_id = None

                if composite_unit_id == unit_id:
                    # as of 'year' (or latest), still assigned to me
                    unit_view.subordinate_units.append(assigned_unit_id)
                
        # Sort on date only.
        unit_view.history.sort(key=lambda historyItem: historyItem[0])
        if cacheYear == None or lastevent_year >= cacheYear:
            # This should prevent getting an older version of the unit
            # stuck in the cache.
            self._unit_view_cache[unit_view.id] = (lastevent_year, unit_view)
        return unit_view        
            
if __name__=="__main__":
    pass # todo create command line interface. Maybe maintenance mode for delete