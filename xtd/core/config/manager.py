# -*- coding: utf-8
# pylint: disable=unused-import
#------------------------------------------------------------------#

__author__    = "Xavier MARCELET <xavier@marcelet.com>"

#------------------------------------------------------------------#

import re
import json
import optparse
import sys

from .formatter        import IndentedHelpFormatterWithNL
from ..error.exception import ConfigValueException, ConfigException
from ..                import mixin

#------------------------------------------------------------------#

class Option:
  def __init__(self, p_section, p_name, p_prop=None):
    self.m_section     = p_section
    self.m_name        = p_name
    self.m_config      = True
    self.m_cmdline     = True
    self.m_default     = None
    self.m_valued      = False
    self.m_description = "undocumented option"
    self.m_checks      = []
    self.m_longopt     = "--%s-%s" % (p_section, p_name)
    self.m_mandatory   = None

    if p_prop is not None:
      self.update(p_prop)

  def update(self, p_props):
    l_keys = [ x[2:] for x in dir(self) if x[0:2] == "m_" ]

    for c_key,c_val in p_props.items():
      if not c_key in l_keys:
        raise ConfigException("invalid option property '%s'" % c_key)
      if c_key == "checks" and not isinstance(c_val, list):
        c_val = [ c_val ]
      setattr(self, "m_%s" % c_key, c_val)

    if self.m_default != None:
      self.m_valued = True
    if not self.m_valued:
      self.m_default = False

  def validate(self, p_value):
    for c_check in self.m_checks:
      p_value = c_check(self.m_section, self.m_name, p_value)
    return p_value

class ConfigManager(metaclass=mixin.Singleton):
  def __init__(self):
    self.m_data          = {}
    self.m_options       = []
    self.m_sections      = {}
    self.m_usage         = "usage: %prog [options]"
    self.m_cmdParser    = None
    self.m_cmdOpts      = None
    self.m_cmdArgs      = []

  def register_section(self, p_section, p_title, p_options):
    self.m_sections[p_section] = p_title
    for c_opt in p_options:
      if not "name" in c_opt:
        raise ConfigException("missing mandatory option property 'name'")
      self.register(p_section, c_opt["name"], c_opt)
    return self

  def register(self, p_section, p_name, p_props):
    l_option = Option(p_section, p_name, p_props)
    self.m_options.append(l_option)
    return self

  def sections(self):
    return self.m_data.keys()

  def section_exists(self, p_section):
    return p_section in self.m_data

  def options(self, p_section):
    if not p_section in self.m_data:
      raise ConfigException("section '%s' dosent exist" % p_section)
    return self.m_data[p_section].keys()

  def option_exists(self, p_section, p_name):
    if not p_section in self.m_data:
      return False
    return p_name in self.m_data[p_section].keys()

  def get(self, p_section, p_name):
    if not p_section in self.m_data or not p_name in self.m_data[p_section]:
      raise ConfigValueException(p_section, p_name, "unknown configuration entry")
    return self.m_data[p_section][p_name]

  def set(self, p_section, p_name, p_value):
    if not p_section in self.m_data or not p_name in self.m_data[p_section]:
      raise ConfigValueException(p_section, p_name, "unknown configuration entry")
    self.m_data[p_section][p_name] = p_value

  def help(self, p_file=None):
    self.m_cmdParser.print_help(p_file)

  def initialize(self):
    self.m_cmdParser    = None
    self.m_cmdOpts      = None
    self.m_cmdArgs      = []
    self.m_data          = {}
    self._load_data()
    self._cmd_parser_create()

  def parse(self, p_argv=None):
    if p_argv is None:
      p_argv = sys.argv
    self._cmd_parser_load(p_argv)
    self._file_parser_load()

  def _get_option(self, p_section, p_name):
    l_values = [ x for x in self.m_options if x.m_section == p_section and x.m_name == p_name ]
    if not len(l_values):
      raise ConfigValueException(p_section, p_name, "unknown configuration entry")
    return l_values[0]

  def _load_data(self):
    for c_option in self.m_options:
      if not c_option.m_section in self.m_data:
        self.m_data[c_option.m_section] = {}
      self.m_data[c_option.m_section][c_option.m_name] = c_option.m_default

  def _cmd_parser_create(self):
    self.m_cmdParser = optparse.OptionParser(usage=self.m_usage,
                                             formatter=IndentedHelpFormatterWithNL())
    l_sections = set([ x.m_section for x in self.m_options ])
    for c_section in sorted(l_sections):
      l_sectionName = self.m_sections.get(c_section, "")
      l_group       = optparse.OptionGroup(self.m_cmdParser, l_sectionName)
      l_options     = [ x for x in self.m_options if x.m_section == c_section and x.m_cmdline ]
      for c_opt in l_options:
        l_args = []
        l_kwds = {
          "help"    : c_opt.m_description,
          "default" : None,
          "action"  : "store",
          "dest"    : "parse_%(section)s_%(key)s" % {
            "section" : c_section,
            "key"     : c_opt.m_name.replace('-', '_')
          }
        }
        if not c_opt.m_valued:
          l_kwds["action"] = "store_true"
        else:
          l_kwds["metavar"] = "ARG"
        if c_opt.m_default != None:
          l_kwds["help"] += " [default:%s]" % str(c_opt.m_default)
        l_args.append(c_opt.m_longopt)
        l_group.add_option(*l_args, **l_kwds)
      self.m_cmdParser.add_option_group(l_group)

  def _cmd_parser_load(self, p_argv):
    self.m_cmdOpts, self.m_cmdArgs = self.m_cmdParser.parse_args(p_argv)
    for c_option in [ x for x in self.m_options if x.m_cmdline ]:
      l_name  = c_option.m_name.replace('-', '_')
      l_value = getattr(self.m_cmdOpts, "parse_%s_%s" % (c_option.m_section, l_name))
      if l_value != None:
        l_value = self._validate(c_option.m_section, c_option.m_name, l_value)
        self.set(c_option.m_section, c_option.m_name, l_value)
      elif c_option.m_mandatory:
        raise ConfigValueException(c_option.m_section, c_option.m_name, "option is mandatory")

  def get_name(self):
    return self.m_cmdArgs[0]

  def get_args(self):
    return self.m_cmdArgs[1:]

  def option_cmdline_given(self, p_section, p_option):
    if self.option_exists(p_section, p_option):
      l_value = getattr(self.m_cmdOpts, "parse_%s_%s" % (p_section, p_option))
      return l_value != None
    return False

  def _file_parser_load(self):
    if not self.section_exists("general") or not self.option_exists("general", "config-file"):
      return
    l_fileName = self._validate("general", "config-file")
    try:
      with open(l_fileName, mode="r", encoding="utf-8") as l_file:
        l_lines = [ x for x in l_file.readlines() if not re.match(r"^\s*//.*" ,x) ]
        l_content = "\n".join(l_lines)
        l_data = json.loads(l_content)
    except Exception as l_error:
      l_message = "invalid json configuration : %s" % str(l_error)
      raise ConfigValueException("general", "config-file", l_message)

    for c_section, c_data in l_data.items():
      for c_option, c_value in c_data.items():
        if not self.option_cmdline_given(c_section, c_option):
          l_value = self._validate(c_section, c_option, c_value)
          self.set(c_section, c_option, l_value)

  def _validate(self, p_section, p_name, p_value = None):
    if p_value is None:
      p_value = self.get(p_section, p_name)
    l_option = self._get_option(p_section, p_name)
    return l_option.validate(p_value)