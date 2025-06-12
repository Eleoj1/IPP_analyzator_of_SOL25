import argparse
import sys

import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET

from lark import Lark, Visitor, Tree
from lark.exceptions import LarkError, UnexpectedToken, UnexpectedCharacters

# Definition of Errors
class SemanticError(Exception):
    pass
class RedefinedError(Exception):
    pass
class ParamAssignError(Exception):
    pass
class ParamMultiError(Exception):
    pass
class MainRunError(Exception):
    pass


# Parsing of command arguments
def print_help():
    print("This program parser language SOL25 and outputs XML tree.")
    print("How to use:")
    print("python3 parse.py --help - for displaying help messsage")
    print('python3 parse.py --source="file" or python3 parse.py --source=file - for parsing a file containing SOL25 code')
    print(" or python3 parse.py - for parsing SOL25 code from stdin")
    sys.exit(0)

def file_path(args):
    #take sol25 from stdin
    if args.source is None:
        source_code = sys.stdin.read()
    else:
        try:
            with open(args.source, "r") as file:
                source_code = file.read()
        except FileNotFoundError:
            print(f"Couldnt find the file", file=sys.stderr)
            sys.exit(11)
    return source_code

def arg_parser():
    if "--help" in sys.argv or "-h" in sys.argv:
        if len(sys.argv) > 2:
            print("Cant use help with other arguments.")
            print(file=sys.stderr)
            sys.exit(10)
        else:
            print_help()

    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    args, unknown_args = parser.parse_known_args()
    if unknown_args:
        print(f"Unrecognized arguments: {unknown_args}", file=sys.stderr) 
        sys.exit(10)
   
    
    return file_path(args)

# Class Visistor
class Visitor_semantic_gen(Visitor):
    def __init__(self,first_comment):
        self.current_class = None
        self.current_method = None
        self.builtin_classes = ["Integer", "String", "Nil", "True", "False"]
        self.object_methods = ["identicalTo:","equalTo:", "asString", "isNumber", "isString","isBlock","isNil"]
        self.nil_methods = ["asString"]
        self.string_methods = ["read", "print", "equalTo", "asString", "asInteger", "concatenateWith:", "startsWith:endsBefore:"]
        self.integer_methods = ["equalTo:", "greaterThan:", "plus:", "minus:", "multiplyBy:", "divBy:", "asString", "asInteger", "timesRepeat:"]
        self.block_methods = ["whileTrue:","value:"]
        self.true_false_methods = ["not", "and:", "or:","ifTrue:ifFalse:"]
        self.keywords = ["nil", "true", "false", "self", "super", "class" ]

        self.classes = {}

        if first_comment is None:
            self.xml_tree = ET.Element("program", language="SOL25")
        else:
            self.xml_tree = ET.Element("program", language="SOL25",description=first_comment.replace('"', ''))

    def program(self,tree):
        #firstly iterate through the whole lark tree and find classes, methods, params
        for new_class in tree.find_data("class_def"):
            if new_class.children[0].value in self.classes:
                raise RedefinedError(f"Redefintion of classes")
           
            self.classes[new_class.children[0].value] = {"methods": {},"superclass": new_class.children[1].value}
            for method in new_class.find_data("method_def"):
                method_name = ""
                # get the full name of the method
                if isinstance(method, Tree):
                    for child in method.children[0].children:
                        if isinstance(child, Tree):
                            for child_tree in child.children:
                                method_name += child_tree.value
                        else:
                            method_name += child.value
                else:
                    method_name = method.value


                if method_name in self.classes[new_class.children[0].value]["methods"]:
                    raise RedefinedError(f"Method is already declared in class")
                # in params the order is important
                self.classes[new_class.children[0].value]["methods"][method_name] = {"vars": set(), "params": [], "exprs" : [{"params": []}]}
                
                # need to separate which params belong to method and which to expression inside of the method
                method_params = []
                for block_param in method.find_data("block_param"):
                    # Without :
                    param_name = block_param.children[0].value[1:] 
                    method_params.append(param_name)

                expr_params = []
                for expr in method.find_data("expr"):
                   
                    for block_param_in_expr in expr.find_data("block_param"):
                        param_name = block_param_in_expr.children[0].value[1:]
                        expr_params.append(param_name)

                #Need to decide which are parametres of methods and which belong to expressions
                # params from expr will also show up in method params
                for param in method_params:
                    if param not in expr_params:
                        
                        if param in self.keywords:
                            raise SyntaxError(f"Parameter cannot be a keyword")
                        elif param in self.classes[new_class.children[0].value]["methods"][method_name]["params"]:
                            raise ParamMultiError(f"Multiple parameteres called the same")
                        if param in self.classes[new_class.children[0].value]["methods"][method_name]["vars"]:
                            raise ParamAssignError(f"Cannot assign a value to a parameter")
                         
                        self.classes[new_class.children[0].value]["methods"][method_name]["params"].append(param)

                for param in expr_params:
                    # was causing issues, setdefault makes sure, that that param does exist
                    self.classes[new_class.children[0].value]["methods"][method_name]["exprs"][-1].setdefault("params", []).append(param)

        # find main and run
        if "Main" not in self.classes:
            raise MainRunError()
        if "run" not in self.classes["Main"]["methods"]:
            raise MainRunError()
        if self.classes["Main"]["methods"]["run"]["params"] != []:
            raise SemanticError(f"Method 'run' cannot have parameters.")


    def class_def(self, tree):
        # start creating the xml tree,
        class_name = tree.children[0].value

        # setting up the current_class attribute to help me orient later
        self.current_class = class_name
        # superclass
        type = tree.children[1].value

        # superclass has to be either one of the predifined classes or one of the classes defined in the program, 
        # which later has to have a predifined superclass
        if type not in ["Object", "Integer", "String", "Nil", "Block", "True", "False"] and type not in self.classes:
            raise ValueError(f"Incorrect superclass.")

        ET.SubElement(self.xml_tree, "class", name=class_name, parent=type)
       

    def method_def(self, tree):
        # iterating till I find the whole name of the method and add a new element to the tree
        # example, compute:and:and:
        method_name = ""
        for child in tree.children[0].children:
            if isinstance(child, Tree):
                for child_tree in child.children:
                    method_name += child_tree.value
            else:
                method_name += child.value

        self.current_method = method_name

        class_el = self.xml_tree.find("class[@name='" + self.current_class + "']")

        ET.SubElement(class_el, "method", selector=method_name)

    def block_stat(self, tree):
        # Skipped param_block, so here i have already passed all params
        params = self.classes[self.current_class]["methods"][self.current_method]["params"]
        method_el = self.find_method(self.current_class, self.current_method)
        
        # if method_elem contains assign something, then, there has to be expr
        expr_el = self.find_expr_el(self.current_class, self.current_method)

        # level deeper, expr in expr
        if expr_el is not None:
            arity = len(self.classes[self.current_class]["methods"][self.current_method]["exprs"][-1]["params"])

            block_el = ET.SubElement(expr_el, "block",arity=str(arity))
            for index, param in enumerate(self.classes[self.current_class]["methods"][self.current_method]["exprs"][-1]["params"]):
                ET.SubElement(block_el, "parameter", order=str(index + 1),name=param)
        else:       
            param_el = ET.SubElement(method_el, "block", arity=str(self.classes[self.current_class]["methods"][self.current_method]["params"].__len__()))
            # Add each param to block arity and order
            for index, param in enumerate(self.classes[self.current_class]["methods"][self.current_method]["params"]):
                ET.SubElement(param_el, "parameter", order=str(index + 1),name=param)

        pass
    def assign_stmt(self, tree):
        # the first has to be an ID = var
        var = tree.children[0].value
        if var in self.keywords:
            raise SyntaxError(f"Var cannot be a keyword")
        # cant assign to params
        if var in self.classes[self.current_class]["methods"][self.current_method]["params"]:
            raise ParamAssignError(f"Cant assign to params.")    
        
        self.classes[self.current_class]["methods"][self.current_method]["vars"].add(var)

        method_el = self.find_method(self.current_class, self.current_method)
        block_ar_elem = method_el.find("block[@arity='" 
                                       + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']")
        # if an expression in an expression, 
        nested_blocks = block_ar_elem.findall(".//block")

        # if nested_blocks is not None:
        if nested_blocks:
            block_ar_elem = nested_blocks[-1]             
            arity = len(nested_blocks[-1].findall("assign")) +1
        else:
            arity = len(method_el.findall("block[@arity='" 
                                          + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']/assign")) +1
        
        assign_order_el =ET.SubElement(block_ar_elem, "assign", order=str(arity))
        ET.SubElement(assign_order_el, "var", name=var)

    def expr(self, tree):
        # number of assigns
        assign_order = self.find_assign_order(self.current_class, self.current_method)
        assign_el = self.xml_tree.find(
            ".//class[@name='" + self.current_class + "']//method[@selector='" 
            + self.current_method + "']/block[@arity='" 
            + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) 
            + "']/assign[@order='" 
            + str(assign_order) 
            + "']"
        )
    
        # dont stack exprs if they are nested
        existing_expr = assign_el.find("expr")
        if existing_expr is None:
            ET.SubElement(assign_el, "expr")

    def expr_tail(self, tree):
        if not isinstance(tree.children[0], Tree):
            if tree.children and (tree.children[0].value in self.keywords and tree.children[0].type == "ID" or tree.children[0].value in self.keywords and tree.children[0].type == "ID_COLON"):
                raise SyntaxError(f"Cannot be a keyword")
            if tree.children[0].type == "ID":
                # spcial case if new
                if tree.children[0].value == "new":
                    expr_el = self.find_expr_el(self.current_class, self.current_method)
                    literal_el = expr_el.find("literal")
                    # found literal, but send has to first
                    if literal_el is not None:
                        expr_el.remove(literal_el)
                        send = ET.SubElement(expr_el, "send", selector=tree.children[0].value)
                        
                        if send is not None:
                            new_expr = ET.SubElement(send, "expr")
                            
                            ET.SubElement(new_expr, literal_el.tag, attrib=literal_el.attrib)
                else:

                    assign_order_el = self.find_all_assign(self.current_class, self.current_method)
                    expr_from_assign = None
                    if assign_order_el is not None:
                        expr_from_assign = assign_order_el[-1].find("expr")
                    
                    if expr_from_assign is not None:
                        # before can either be send, var or literal
                        if expr_from_assign is not None:
                            last_var = expr_from_assign.find("var")
                            if last_var is not None:

                                # add arg order, add, the new method, expr
                                send_el = expr_from_assign.find("send")
                                if send_el is not None:
                                    num_args = len(send_el.findall("arg")) +1
                                    new_arg = ET.SubElement(send_el, "arg", order=str(num_args))
                                    new_expr = ET.SubElement(new_arg, "expr")
                                    new_send = ET.SubElement(new_expr, "send", selector=tree.children[0].value)
                                    expr_from_assign.remove(last_var)
                                    another_expr = ET.SubElement(new_send, "expr")
                                    another_expr.append(last_var)


                                else:
                                    # no send, so no arg
                                    new_send = ET.SubElement(expr_from_assign, "send", selector=tree.children[0].value)
                                    new_expr = ET.SubElement(new_send, "expr")
                                    expr_from_assign.remove(last_var)
                                    ET.SubElement(new_expr, last_var.tag, attrib=last_var.attrib)
                            else:
                                # could not find var, so look for literal
                                literal = expr_from_assign.find("literal")
                                if literal is not None:
                                    val = literal.attrib.get("value")
                                    self.check_builtin_methods(tree.children[0].value, val)
                                    # not in build in classes, look for parent
                                    real_parent, parent_class = self.find_real_parent(val)
                                    self.check_builtin_methods(tree.children[0].value, parent_class)
                                    expr_from_assign.remove(literal)
                                    new_send = ET.SubElement(expr_from_assign, "send", selector=tree.children[0].value)
                                    new_expr = ET.SubElement(new_send, "expr")
                                    ET.SubElement(new_expr, literal.tag, attrib=literal.attrib)
                                    
                                    
                    else:
                        # no expr but there should be atleast send
                        method_el = self.xml_tree.find(".//class[@name='" + self.current_class + "']//method[@selector='" + self.current_method + "']/block[@arity='" 
                                                       + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']/assign[@order='" 
                                                       + str(len(self.classes[self.current_class]["methods"][self.current_method]["vars"])) + "']/expr/literal[@class]")
                        orig_class = method_el.attrib.get("value" ) 
                        self.check_builtin_methods(tree.children[0].value, orig_class)
                        #new subelement
                        parent  = self.classes[method_el.attrib.get("value" )].get("superclass")
                        self.check_builtin_methods(tree.children[0].value, parent)
                        if parent not in self.builtin_classes:
                            # find parents real class
                            real_parent, parent_clss = self.find_real_parent(parent)
                            if real_parent is None:
                                raise ValueError(f"Class is not defined.")
                        
                            self.check_builtin_methods(tree.children[0].value, parent_clss)


                            # find literal, and exchange
                            expr_el = self.find_expr_el(self.current_class, self.current_method)
                            expr_el.remove(method_el)
                            new_method_el = ET.SubElement(expr_el,"send", selector=tree.children[0].value)
                            new_expr = ET.SubElement(new_method_el, "expr")
                            ET.SubElement(new_expr, method_el.tag, attrib=method_el.attrib)

    def expr_sel(self, tree):
        # sending message to the object
        if tree.children:
                if tree.children[0].value == "from:":
                    expr_el = self.xml_tree.find(".//class[@name='" + self.current_class + "']//method[@selector='" + self.current_method + "']/block[@arity='"
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']/assign[@order='" 
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["vars"])) + "']/expr")
                    literal_el = expr_el.find("literal")
                    if literal_el is not None:
                        expr_el.remove(literal_el)
                        send = ET.SubElement(expr_el, "send", selector=tree.children[0].value)
                        new_expr = ET.SubElement(send, "expr")
                        ET.SubElement(new_expr, "literal", attrib=literal_el.attrib)
                        arg_el = ET.SubElement(send, "arg", order="1")
                        another_expr = ET.SubElement(arg_el, "expr")
                        if literal_el.attrib.get("value") == "class":
                            new_class = literal_el.attrib.get("class")
                        else:
                            new_class = literal_el.attrib.get("value")
                        ET.SubElement(another_expr, "literal", attrib={"class": new_class})
                else:
                    # what kind of message is it
                    method = tree.children[0].value
                    expr_el = self.find_expr_el(self.current_class, self.current_method)
                    if expr_el is not None:
                         # if its built in class
                        # message, has to be linked with something, probably a literal
                        if expr_el.find("literal") is not None:
                            class_name = expr_el.find("literal").attrib.get("value")
                            if class_name in self.builtin_classes:
                                self.check_builtin_methods(method, class_name)
                            else:
                                parent =expr_el.find("literal").attrib.get("class")

                                self.check_builtin_methods(method, parent)
                        else:
                            #  no literal
                            # look for send
                            send_method = expr_el.find("send")
                            if send_method is not None:
                                # look at the next element to find out to which class it belongs
                                if isinstance(tree.children[1], Tree):
                                    for child in tree.children[1].children:
                                        type = None
                                        if child.type == "CLASS_ID":
                                            type = "class"
                                        elif child.type == "ID":
                                            type = "var"
                                        elif child.type == "STRING":
                                            type = "String"
                                        elif child.type == "INT":
                                            type = "Integer"
                                        if type is not None:
                                            self.check_builtin_methods(method, type)

                                # needs to go higher then previsous send
                                # if its on of the partial methods
                                stored_method_children = list(send_method)
                                expr_el.remove(send_method)
                                new_send = ET.SubElement(expr_el, "send", selector=method)
                                new_expr = ET.SubElement(new_send, "expr")
                                new_send =ET.SubElement(new_expr, send_method.tag, attrib=send_method.attrib)
                                for child in stored_method_children:
                                    new_send.append(child)
                                return

                    # var is left
                    method_send =ET.SubElement(expr_el, "send", selector=method)
                    #now exchange var and method
                    var_element = expr_el.find("var")

                    if var_element is not None:
                        expr_el.remove(var_element)
                        new_expr = ET.SubElement(method_send, "expr")
                        ET.SubElement(new_expr, "var", name=var_element.attrib.get("name"))

    def expr_base(self, tree):
        if isinstance(tree.children[0], Tree):
            return 
        from_el = self.xml_tree.find(".//class[@name='" + self.current_class + "']//method[@selector='" + self.current_method + "']/block[@arity='"
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']/assign[@order='" 
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["vars"])) + "']/expr/send[@selector='from:']")
        # special handling of from
        if from_el is not None:
            arg_el = from_el.find("arg")
            if arg_el is not None:
                expr_el = arg_el.find("expr")
                if expr_el is not None:
                    literal_el = expr_el.find("literal")
                    if literal_el is not None:
                        expr_el.remove(literal_el)
                        class_name = literal_el.attrib.get("class")
                        ET.SubElement(expr_el, "literal", attrib={"class": class_name, "value": tree.children[0].value})
        
        else:
            is_send_method = False
            method_el = self.find_method(self.current_class, self.current_method)

            expr_el = self.find_expr_el(self.current_class, self.current_method)

            send_method = self.xml_tree.find(".//class[@name='" + self.current_class + "']//method[@selector='" + self.current_method + "']/block[@arity='"
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["params"])) + "']/assign[@order='" 
                                        + str(len(self.classes[self.current_class]["methods"][self.current_method]["vars"])) + "']/expr/send[@selector]")
            if send_method is not None:
                is_send_method = True
            
            #based on Terminal, decide what the type is
            var = None
            if tree.children[0].type == "CLASS_ID":
                if tree.children[0].value not in self.classes and tree.children[0].value not in self.builtin_classes:
                    raise ValueError(f"Error: Class '{tree.children[0].value}' is not defined")
                type = "class"
                    
                var = tree.children[0].value
            if tree.children[0].type == "ID":
                var = tree.children[0].value
                if var not in self.keywords and var != "self" and var != "super":
                    if tree.children[0].value not in self.classes[self.current_class]["methods"][self.current_method]["vars"] and tree.children[0].value not in self.classes[self.current_class]["methods"][self.current_method]["params"]:
                        raise ValueError(f"Used undefined var.")
                type_list = { "nil": "Nil", "true": "True", "false": "False"}
                type = type_list.get(tree.children[0].value, "var")
            elif tree.children[0].type == "STRING":
                type = "String"
                var = tree.children[0].value
                # change the formatting a littel bit
                var =var.replace("\\'", "&apos;")
                var = var.replace("'","")

                # if var
            elif tree.children[0].type == "INT":
                type = "Integer"
            if var is None:
                var = tree.children[0].value

            expr_el = self.find_expr_el(self.current_class, self.current_method)
            
            # if next is id_colon, then it has to be send 
            if is_send_method:
                # check number of params

                send_method_name = send_method.attrib.get("selector")
                # check if its a method 
                if send_method_name not in self.classes[self.current_class]["methods"]:
                    for method in self.classes[self.current_class]["methods"]:
                        if send_method_name in method:
                            send_method_name = method
                            send_method.set("selector", send_method_name)

                if send_method_name in self.integer_methods:
                    num_params = 1
                elif send_method_name in self.string_methods:
                    num_params = 1  
                elif send_method_name in self.object_methods:
                    num_params = 1
                elif send_method_name in self.nil_methods:
                    num_params = 1
                elif send_method_name in self.block_methods:
                    num_params = 1
                elif send_method_name in self.true_false_methods:
                    num_params = 1
                else:
                    if send_method_name == "vysl:" or send_method_name == "value:" or send_method_name == "vysl":
                        num_params = 1
                    else:

                        num_params = len(self.classes[self.current_class]["methods"][send_method_name]["params"])

                # dont base it on send,but on assign order, then arg order
                # in send  method find assign order
                assign_orders = method_el.findall(".//block/assign")
                args = [] 

                if assign_orders:
                    last_assign = assign_orders[-1] 
                    send_el = last_assign.find(f".//expr/send[@selector='{send_method_name}']")

                    if send_el is not None:
                        args = send_el.findall("arg")
                    else:
                        # no send the last assign
                        # add new sub,but to the last assign
                        var_from_last_assign = last_assign.find("var")
                        expr_from_last_assign = last_assign.find("expr")
                        if var_from_last_assign is not None:
                            ET.SubElement(expr_from_last_assign, "var", name = var)
                        else:
                            
                            ET.SubElement(expr_from_last_assign, "var",name = tree.children[0].value)
                        return
                # args = []
                order_num = len(args) + 1
                if order_num > num_params:
                    raise SemanticError("Too many arguments in method call.")

                arg_el = ET.SubElement(send_method, "arg", order=str(order_num))
                expr = ET.SubElement(arg_el, "expr")

                ET.SubElement(expr, "literal", attrib={"class": "class", "value": tree.children[0].value})
                # if the method had multiple params
                if not any(isinstance(child, Tree) and child.data == "expr_sel" for child in tree.children):
                    if order_num < num_params:

                        colon_num = send_method_name.count(":")
                        if colon_num != num_params:
                            raise SemanticError("Too few arguments in method call.")

            elif type =="var" or type == "self" or type == "super":
                ET.SubElement(expr_el, "var", name=var) 
            else:
                ET.SubElement(expr_el, "literal", attrib={"class": type, "value": var})


    # Helper methods to find elements in xml tree
    def find_method(self,class_name, method_name):
        return self.xml_tree.find(".//class[@name='" + class_name + "']//method[@selector='" + method_name + "']")
    
    def find_all_assign(self,class_name, method_name):
        method_el = self.find_method(class_name, method_name)
        return method_el.findall("block[@arity='" + str(len(self.classes[class_name]["methods"][method_name]["params"])) 
                                 + "']/assign")
    
    def find_expr_el(self,class_name, method_name):
        method_el = self.find_method(class_name, method_name)
        return method_el.find("block[@arity='" + str(len(self.classes[class_name]["methods"][method_name]["params"])) + 
                              "']/assign[@order='"
                              + str(len(self.find_all_assign(class_name, method_name))) + "']/expr")
        
    def find_assign_order(self, class_name, method_name):
        return len(self.xml_tree.findall(
            ".//class[@name='" + class_name+ "']//method[@selector='" 
            + method_name + "']/block[@arity='" 
            + str(len(self.classes[class_name]["methods"][method_name]["params"])) 
            + "']/assign"))
    

    def sel(self, tree):
        if tree.children[0].value in self.keywords:
            raise SyntaxError(f"Selector cannot be a keyword")

    # find the parent that definitevely builtin
    def find_real_parent(self, parent):
        for class_from_all in self.classes:
            if class_from_all == parent:
                superclass = self.classes[class_from_all]["superclass"]
                
                if superclass not in self.builtin_classes:
                    return self.find_real_parent(superclass)
                return class_from_all, superclass

        return None, None

    # Methods goes through all possible builtin classes and check if the methods isnt builtin
    def check_builtin_methods(self, method_name, class_name):
        if class_name == "Integer":
            if method_name not in self.integer_methods:
                raise ValueError
        elif class_name == "String":
            if method_name not in self.string_methods:
                raise ValueError
        elif class_name == "Object":
            if method_name not in self.object_methods:
                raise ValueError
        elif class_name == "Nil":
            if method_name not in self.nil_methods:
                raise ValueError
        elif class_name == "Block":
            if method_name not in self.block_methods:
                raise ValueError
        elif class_name == "True" or class_name == "False":
            if method_name not in self.true_false_methods:
                raise ValueError
            
    # Fixes the formatting of xml and prints it to stdout
    def format_print_xml_tree(self):
        raw_xml = ET.tostring(self.xml_tree, encoding="unicode", method="xml")
        pretty_xml = minidom.parseString(raw_xml)
        final_output = pretty_xml.toprettyxml(indent="  ", encoding='utf-8')
        final_output = final_output.decode('utf-8')
        final_output = final_output.replace("&amp;apos;", "&apos;")
        final_output = final_output.rstrip("\n")
        print(final_output)

if __name__ == "__main__":

    #parse arguments
    code = arg_parser()
    grammar = r"""
        program: class_def*
        class_def: "class" CLASS_ID ":" CLASS_ID "{" method_def* "}"
        method_def: sel "[" method_body "]"
        method_body: [block_param*] "|" block_stat
        block_param: COLON_ID
        block_stat: (assign_stmt)*
        assign_stmt: ID ":=" expr "."
        expr: expr_base expr_tail
        expr_base: INT | STRING | ID | CLASS_ID |"(" expr ")" | "[" method_body "]"
        expr_tail: ID | expr_sel
        expr_sel: ID_COLON expr_base expr_sel | 
        sel: ID | ID_COLON sel_tail
        sel_tail: (ID_COLON)*

        
        COLON_ID:/:[a-z_][a-zA-Z0-9_]*/
        ID_COLON: /[a-z_][a-zA-Z0-9_]*:/
        CLASS_ID: /[A-Z][a-zA-Z0-9_]*/ 
        ID: /[a-z_][a-zA-Z0-9_]*/
        INT: /-?\d+/

        STRING: /'([^'\\\n]|\\[n\\'])*'/
        COMMENT: /"[^"]*"/
        %import common.WS
        %ignore WS
        %ignore COMMENT
    """
    # Lexer callback to get the first comment
    def lexer_callback(token):
        if first_comment[0] is None:
            first_comment[0] = token.value

    first_comment = [None]
    parser = Lark(
        grammar,
        start="program",
        lexer="contextual",
        parser	= "lalr",
        lexer_callbacks={"COMMENT": lexer_callback}  
    )
   
    try:
        tree = parser.parse(code)
        try:
            visitor = Visitor_semantic_gen(first_comment[0])
            visitor.visit_topdown(tree)

            visitor.format_print_xml_tree()
        except MainRunError as e:
            print(f"No main or main with method run",file=sys.stderr)
            sys.exit(31)
        except ValueError as e:
            print(f"Semantic Error: {e}",file=sys.stderr)
            sys.exit(32)
        except RedefinedError as e:
            print(f"Semantic Error: {e}",file=sys.stderr)
            sys.exit(35)
        except SyntaxError as e:
            print(f"syntax Error from visitor: {e}",file=sys.stderr)
            sys.exit(22)
        except SemanticError as e:
            print(f"Semantic Error: {e}",file=sys.stderr)
            sys.exit(33)
        except ParamAssignError as e:
            print(f"Semantic Error: {e}",file=sys.stderr)
            sys.exit(34)
        except ParamMultiError as e:
            print(f"Semantic Error: {e}",file=sys.stderr)
            sys.exit(35)

    except UnexpectedToken as e:
        print(f"Syntax Error", file=sys.stderr)
        sys.exit(22)
    except UnexpectedCharacters as e:
        print(f"Lexical Error", file=sys.stderr)
        sys.exit(21) 
    except LarkError as e:
        print(f"Error during parsing: {e}", file=sys.stderr)
        sys.exit(35) 
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(99)
