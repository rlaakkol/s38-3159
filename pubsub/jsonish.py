"""
    The abomination that is not JSON.

    Serious wheel-reinventing in progress.
"""

import logging; log = logging.getLogger('pubsub.jsonish')

class ParseError (Exception) :
    pass

def parse_next (iter) :
    while True :
        c = next(iter, None)
        
        if c is None :
            break
        elif c.isspace() :
            continue
        else :
            return c

def parse_str (c0, iter) :
    """
        Parse ' -> yield char

        >>> list(parse_str("'", iter("foo'")))
        ['f', 'o', 'o']
    """

    while True :
        c = next(iter, None)

        if c is None :
            raise ParseError("end-of-string")

        elif c == c0 :
            return
        else :
            yield c

def parse_number (c, iter) :
    """
        Parse number representation -> int/float
    """

    str = c

    while True :
        c = next(iter, None)
        
        if not c :
            break

        elif c == '.' or c.isdigit() :
            str += c
        else :
            break

    if '.' in str :
        return c, float(str)
    else :
        return c, int(str)

def parse_list (c, iter) :
    """
        Parse [ -> yield item

        >>> list(parse_list("[", iter("'foo', 'bar']")))
        ['foo', 'bar']
    """

    while True :
        c = parse_next(iter)

        if c == ']' :
            break

        item, c = parse_item(c, iter)
        
        if item is not None :
            yield item

        if c == ',' :
            continue

        elif c == ']' :
            break

        else :
            raise ParseError("invalid item-sep: {c}".format(c=c))

def parse_dict (c, iter) :
    """
        Parse { -> yield key, value

        >>> list(parse_dict("{", iter("'key': 'value'}")))
        [('key', 'value')]
    """

    while True :
        c = parse_next(iter)

        if c == '}' :
            break

        key, c = parse_item(c, iter)
        
        if c != ':' :
            raise ParseError("invalid key-sep: {c}".format(c=c))

        c = parse_next(iter)
        value, c = parse_item(c, iter)
            
        yield key, value

        if c == ',' :
            continue

        elif c == '}' :
            break

        else :
            raise ParseError("invalid keyval-sep: {c}".format(c=c))

def parse_item (c, iter) :
    """
        Parse iterable -> value        
    """

    if c is None :
        val = None

    elif c == "'" :
        val = ''.join(parse_str(c, iter))
        c1 = parse_next(iter)

    elif c in '+-' or c.isdigit() :
        c1, val = parse_number(c, iter)
    
    elif c == '[' :
        val = list(parse_list(c, iter))
        c1 = parse_next(iter)

    elif c == '{' :
        val = dict(parse_dict(c, iter))
        c1 = parse_next(iter)

    else :
        raise ParseError("invalid start-token: {c}".format(c=c))
        
    log.debug("%s -> %r -> %s", c, val, c1)

    return val, c1

def parse (str) :
    """
        Parse str -> value

        >>> parse("'foo'")
        'foo'
        >>> parse("1234")
        1234
        >>> parse("[]")
        []
        >>> parse("['foo', 'bar']")
        ['foo', 'bar']
        >>> parse("{}")
        {}
        >>> parse("{'foo': 'bar'}")
        {'foo': 'bar'}
    """

    i = iter(str)
    c = parse_next(i)

    val, c = parse_item(c, i)

    return val

def parse_bytes (bytes) :
    """
        Parse bytes -> value
    """

    # XXX: need to handle binary data...
    return parse(bytes.decode('ascii'))

def build_string (str) :
    yield "'"
    yield str
    yield "'"

def build_number (num) :
    yield str(num)

def build_list (list) :
    start = True

    yield '['

    for item in list :
        if start :
            start = False
        else :
            yield ','

        for token in build_item(item) :
            yield token
    
    yield ']'

def build_dict (dict) :
    start = True

    yield '{'

    for key, value in dict.items() :
        if start :
            start = False
        else :
            yield ','

        for token in build_item(key) :
            yield token

        yield ':'

        for token in build_item(value) :
            yield token

    yield '}'

def build_item (item) :
    """
        Build item -> yield str

        >>> list(build_item(1234))
        ['1234']
        >>> list(build_item('foo'))
        ["'", 'foo', "'"]
        >>> list(build_item([1, 2]))
        ['[', '1', ',', '2', ']']
        >>> list(build_item({1: 2}))
        ['{', '1', ':', '2', '}']
    """

    if isinstance(item, str) :
        return build_string(item)

    elif isinstance(item, (int, float)) :
        return build_number(item)

    elif isinstance(item, (list, tuple)) :
        return build_list(item)

    elif isinstance(item, dict) :
        return build_dict(item)

    else :
        raise ValueError("invalid item: {item!r}".format(item=item))

def build_str (item) :
    return ''.join(build_item(item))

def build_bytes (item) :
    return build_str(item).encode('ascii')

if __name__ == '__main__':
    import doctest
    logging.basicConfig(level=logging.DEBUG)
    doctest.testmod()

