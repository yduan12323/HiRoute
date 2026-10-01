"""Small explicit taxonomy; no quality or unobserved activity inference."""
def classify_tags(tags, extraction):
    if tags.get('access') in extraction['exclude_access']:
        return frozenset(), None
    capabilities, subtypes = set(), []
    for key, mapping in extraction['taxonomy'].items():
        value = tags.get(key)
        if value in mapping:
            if key == 'amenity' and value == 'parking':
                capacity = tags.get('capacity', '')
                if capacity.isdigit() and int(capacity) < extraction['parking_min_explicit_capacity']:
                    continue
            capabilities.update(mapping[value])
            subtypes.append(f'{key}={value}')
    return frozenset(capabilities), ';'.join(sorted(subtypes)) or None


def filter_expressions(extraction):
    return [f'nwr/{key}={",".join(sorted(values))}' for key, values in sorted(extraction['taxonomy'].items())]
