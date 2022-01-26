import json

class CivGameData:
    def __init__(self, game_data_file=None):
        self._game_data_file = game_data_file
        self._game_data = {
            "unit_types":{},
            "promotion_types":{}
        }
        self.reload()
        
    def reload(self):
        if not self._game_data_file:
            return
        with open(self._game_data_file) as f:
            self._game_data = json.load(f)
            
    def save(self, rename=None):
        if rename:
            self._game_data_file = rename
        if not self._game_data_file:
            raise Exception("Cannot save game data without a specified json file")
        with open(self._game_data_file, "w+") as f:
            json.dump(self._game_data, f, indent=4, sort_keys=True)
    
    def set_unit_type(self, unit_type_name, unit_display_name, unit_class, strength, move, cost, overwrite=False ):
        if not overwrite and unit_type_name in self._game_data["unit_types"]:
            raise Exception("Duplicate unit type {} (overwrite not enabled).".format(unit_type_name))
        self._game_data["unit_types"][unit_type_name] = {
            "display": unit_display_name,
            "class": unit_class,
            "strength": strength,
            "move": move,
            "cost": cost
        }
        
    def get_unit_type(self, unit_type_name):
        return self._game_data["unit_types"].get(unit_type_name, None)
        
    def del_unit_type(self, unit_type_name):
        if unit_type_name not in self._game_data["unit_types"]:
            raise Exception("No such unit type {} to delete.".format(unit_type_name))
        del self._game_data["unit_types"][unit_type_name]
    
    def removeUnitType(self, unitTypeName):
        self._unitDb.execute("DELETE from unit_types WHERE name='%s'" % unitTypeName)
            
    def get_unit_types(self):
        return list(self._game_data["unit_types"].keys())
    
    def add_promotion(self, promotion_name):
        if promotion_name in self._game_data["promotions"]:
            raise Exception("Duplicate promotion {}, cannot add".format(promotion_name))
        self._game_data["promotions"].append(promotion_name)
    
    def del_promotion(self, promotion_name):
        if promotion_name not in self._game_data["promotions"]:
            raise Exception("Promotion {} not found, cannot delete".format(promotion_name))
        self._game_data["promotions"].remove(promotion_name)
            
    def get_promotions(self):
        return self._game_data["promotions"]