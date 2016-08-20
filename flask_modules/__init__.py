#!/usr/bin/env python
# -*- coding: utf-8 -*-
from connexion.operation import Operation
from connexion.resolver import Resolver, Resolution


class SimpleResolver(Resolver):
    def __init__(self, module):
        self._module = module

    def resolve(self, operation: Operation):
        parts = []
        if operation.path == '/':
            parts.append('root')
        else:
            for part in operation.path.split('/'):
                if part:
                    parts.append(part)
        parts.append(operation.method)
        func_name = '_'.join(parts).replace('{', '').replace('}', '')
        func = getattr(self._module, func_name)

        return Resolution(func, func_name)


def function_resolver(module):
    """why is this not standard???"""

    def fetch_function(name):
        print(name)
        getattr(module, name)

    return fetch_function


def annotation_composer(*decs):
    def deco(f):
        for dec in reversed(decs):
            f = dec(f)
        return f

    return deco
