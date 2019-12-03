## @tdoc:indent spaces=2
## title: TDoc embedded documentation
## content|texto
##   So this is an example of a *TDoc* document embedded in the comments
##   of a Python program.

## section#functions title="Function definition"
##   function#hello_world
##     param name=message type=str default="Hello, world"
##        The message to be displayed
##     :
def hello_world(message='Hello, world!'):
    """Prints 'Hello, world!'."""
    print (message)

## section#main title="Main section"
##   .

if __name__ == "__main__":
    hello_world()

# EOF
