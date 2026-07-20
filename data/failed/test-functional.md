# Python Decorators

Python decorators are a powerful feature that allows you to modify the behavior of functions or classes. They provide a simple syntax for calling higher-order functions.

## Key Concepts

1. **Function Decorators**: Functions that take a function as input and return a new function
2. **Class Decorators**: Classes that take a class as input and return a modified class
3. **Decorator Syntax**: Using `@decorator` syntax above a function definition

## Example

```python
def my_decorator(func):
    def wrapper():
        print("Before function call")
        func()
        print("After function call")
    return wrapper

@my_decorator
def say_hello():
    print("Hello!")
```

## Use Cases

- Logging
- Timing
- Authentication
- Caching
- Rate limiting
