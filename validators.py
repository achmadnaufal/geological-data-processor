"""
Data validators for geological module.

Handles validation and quality checks for domain-specific data.
"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Optional


class GeologicalValidator:
    """
    Validator for geological data.
    
    Ensures data quality, consistency, and domain-specific constraints.
    """
    
    def __init__(self):
        """Initialize validator with default constraints."""
        pass
    
    def validate_record(self, record: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a single record.
        
        Args:
            record: Dictionary with field values
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required fields
        required_fields = ['location', 'depth_m', 'rock_type', 'mineral_content']
        for field in required_fields:
            if field not in record:
                errors.append(f"Missing required field: {field}")
            elif record[field] is None or (isinstance(record[field], str) and not record[field].strip()):
                errors.append(f"Field {field} cannot be empty")
        
        # Check numeric fields are numeric
        for key, value in record.items():
            if isinstance(value, (int, float)) and value < 0:
                # Allow negative for certain fields
                if 'adjustment' not in key.lower() and 'change' not in key.lower():
                    errors.append(f"{key}: negative value {value} not allowed")
        
        return len(errors) == 0, errors
    
    def validate_dataframe(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate entire DataFrame.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check for missing values
        missing = df.isnull().sum()
        if missing.any():
            for col, count in missing[missing > 0].items():
                issues.append(f"{col}: {count} missing values ({(count/len(df)*100):.1f}%)")
        
        # Check for duplicates
        duplicate_count = df.duplicated().sum()
        if duplicate_count > 0:
            issues.append(f"{duplicate_count} duplicate rows found")
        
        # Validate each row
        for idx, row in df.iterrows():
            record = row.to_dict()
            is_valid, row_errors = self.validate_record(record)
            if not is_valid:
                for error in row_errors:
                    issues.append(f"Row {idx}: {error}")
        
        return len(issues) == 0, issues


if __name__ == "__main__":
    import doctest
    doctest.testmod()
