"""Fusion document attribute storage for bend settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import adsk.fusion

# Attribute group name for all our data
ATTR_GROUP = 'TubeBendSheet'


@dataclass(slots=True)
class TubeSettings:
    """Settings stored on a tube path for bend calculation."""
    bender_id: str = ""
    die_id: str = ""
    tube_od: float = 0.0
    precision: int = 16
    travel_reversed: bool = False
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            'bender_id': self.bender_id,
            'die_id': self.die_id,
            'tube_od': self.tube_od,
            'precision': self.precision,
            'travel_reversed': self.travel_reversed,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> TubeSettings:
        """Deserialize from JSON string."""
        try:
            data = json.loads(json_str)
            return cls(
                bender_id=data.get('bender_id', ''),
                die_id=data.get('die_id', ''),
                tube_od=data.get('tube_od', 0.0),
                precision=data.get('precision', 16),
                travel_reversed=data.get('travel_reversed', False),
            )
        except (json.JSONDecodeError, KeyError):
            return cls()


class AttributeManager:
    """
    Manages attributes stored on Fusion 360 entities.
    
    Stores tube bend settings on sketches or components so they
    persist with the document.
    """
    
    SETTINGS_ATTR = 'tubeSettings'
    
    @staticmethod
    def save_settings(entity: 'adsk.fusion.SketchCurve | adsk.fusion.SketchEntity | adsk.fusion.Component',
                      settings: TubeSettings) -> bool:
        """
        Save tube settings to an entity.
        
        Args:
            entity: A sketch entity or component to store settings on
            settings: The settings to save
            
        Returns:
            True if successful
        """
        try:
            # Get the parent sketch or component
            target = AttributeManager._get_attribute_target(entity)
            if target is None:
                return False
            
            # Remove existing attribute if present
            existing = target.attributes.itemByName(ATTR_GROUP, AttributeManager.SETTINGS_ATTR)
            if existing:
                existing.deleteMe()
            
            # Add new attribute
            target.attributes.add(ATTR_GROUP, AttributeManager.SETTINGS_ATTR, settings.to_json())
            return True

        except Exception as e:
            import traceback
            print(f"Warning: Failed to save tube settings: {e}")
            print(traceback.format_exc())
            return False
    
    @staticmethod
    def load_settings(entity: 'adsk.fusion.SketchCurve | adsk.fusion.SketchEntity | adsk.fusion.Component') -> TubeSettings | None:
        """
        Load tube settings from an entity.
        
        Args:
            entity: A sketch entity or component to load settings from
            
        Returns:
            TubeSettings if found, None otherwise
        """
        try:
            target = AttributeManager._get_attribute_target(entity)
            if target is None:
                return None
            
            attr = target.attributes.itemByName(ATTR_GROUP, AttributeManager.SETTINGS_ATTR)
            if attr is None:
                return None
            
            return TubeSettings.from_json(attr.value)

        except Exception as e:
            import traceback
            print(f"Warning: Failed to load tube settings: {e}")
            print(traceback.format_exc())
            return None

    @staticmethod
    def clear_settings(entity: 'adsk.fusion.SketchCurve | adsk.fusion.SketchEntity | adsk.fusion.Component') -> bool:
        """
        Remove tube settings from an entity.
        
        Returns:
            True if settings were found and removed
        """
        try:
            target = AttributeManager._get_attribute_target(entity)
            if target is None:
                return False
            
            attr = target.attributes.itemByName(ATTR_GROUP, AttributeManager.SETTINGS_ATTR)
            if attr:
                attr.deleteMe()
                return True
            return False

        except Exception as e:
            import traceback
            print(f"Warning: Failed to clear tube settings: {e}")
            print(traceback.format_exc())
            return False

    @staticmethod
    def _get_attribute_target(
        entity: 'adsk.fusion.SketchCurve | adsk.fusion.SketchEntity | adsk.fusion.Component'
    ) -> 'adsk.fusion.Sketch | adsk.fusion.Component | None':
        """
        Get the appropriate target for storing attributes.

        For sketch entities, we store on the parent sketch.
        For components, we store on the component itself.

        Args:
            entity: A sketch entity (line or arc) or component

        Returns:
            The parent sketch for sketch entities, the component itself for
            components, or None if the entity type is not recognized.
        """
        import adsk.fusion

        # If it's a component, use it directly
        if isinstance(entity, adsk.fusion.Component):
            return entity

        # If it's a sketch entity, use the parent sketch
        if hasattr(entity, 'parentSketch') and entity.parentSketch:
            return entity.parentSketch

        return None
