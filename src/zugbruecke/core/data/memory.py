# -*- coding: utf-8 -*-

"""

ZUGBRUECKE
Calling routines in Windows DLLs from Python scripts running on unixlike systems
https://github.com/pleiszenburg/zugbruecke

	src/zugbruecke/core/data/memory.py: (Un-) packing of argument pointers

	Required to run on platform / side: [UNIX, WINE]

	Copyright (C) 2017-2018 Sebastian M. Ernst <ernst@pleiszenburg.de>

<LICENSE_BLOCK>
The contents of this file are subject to the GNU Lesser General Public License
Version 2.1 ("LGPL" or "License"). You may not use this file except in
compliance with the License. You may obtain a copy of the License at
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt
https://github.com/pleiszenburg/zugbruecke/blob/master/LICENSE

Software distributed under the License is distributed on an "AS IS" basis,
WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for the
specific language governing rights and limitations under the License.
</LICENSE_BLOCK>

"""


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# IMPORT
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

import ctypes
#from pprint import pformat as pf
#import traceback

from ..memory import (
	generate_pointer_from_bytes,
	overwrite_pointer_with_bytes,
	serialize_pointer_into_bytes
	)

WCHAR_BYTES = ctypes.sizeof(ctypes.c_wchar)


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CLASS: Memory content packing and unpacking
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class memory_class():


	def client_fix_memsync_ctypes(self, memsync_d_list):

		# Iterate over memory segments, which must be kept in sync
		for memsync_d in memsync_d_list:

			# Defaut type, if nothing is given, is unsigned byte
			if '_t' not in memsync_d.keys():
				memsync_d['_t'] = ctypes.c_ubyte


	def client_pack_memory_list(self, args_tuple, memsync_d_list):

		# Start empty package for transfer
		mem_package_list = []

		# Store pointers locally so their memory can eventually be overwritten
		memory_handle = []

		# Iterate over memory segments, which must be kept in sync
		for memsync_d in memsync_d_list:

			# Pack data for one pointer
			item_data, item_pointer = self.__pack_memory_item__(args_tuple, memsync_d)

			# Append data to package
			mem_package_list.append(item_data)

			# Append actual pointer to handler list
			memory_handle.append(item_pointer)

		return mem_package_list, memory_handle


	def client_unpack_memory_list(self, mem_package_list, memory_handle):

		# Overwrite the local pointers with new data
		for pointer_index, pointer in enumerate(memory_handle):
			overwrite_pointer_with_bytes(pointer, mem_package_list[pointer_index])


	def server_pack_memory_list(self, memory_handle, memsync_d_list):

		# Generate new list for arrays of ints to be shipped back to the client
		mem_package_list = []

		# Iterate through pointers and serialize them
		for pointer, memsync_d in zip(memory_handle, memsync_d_list):

			memory_bytes = serialize_pointer_into_bytes(*pointer)

			if 'w' in memsync_d.keys():
				memory_bytes = self.__adjust_wchar_length__(
					memory_bytes, WCHAR_BYTES, memsync_d['w']
					)

			mem_package_list.append(memory_bytes)

		return mem_package_list


	def server_unpack_memory_list(self, args_tuple, arg_memory_list, memsync_d_list):

		# Generate temporary handle for faster packing
		memory_handle = []

		# Iterate over memory segments, which must be kept in sync
		for memory_bytes, memsync_d in zip(arg_memory_list, memsync_d_list):

			# Search for pointer
			pointer = self.__get_argument_by_memsync_path__(args_tuple, memsync_d['p'][:-1])

			if 'w' in memsync_d.keys():
				memory_bytes = self.__adjust_wchar_length__(
					memory_bytes, memsync_d['w'], WCHAR_BYTES
					)

			if isinstance(memsync_d['p'][-1], int):
				# Handle deepest instance
				pointer[memsync_d['p'][-1]] = generate_pointer_from_bytes(memory_bytes)
				# Append to handle
				memory_handle.append((pointer[memsync_d['p'][-1]], len(memory_bytes)))
			else:
				# Handle deepest instance
				setattr(pointer.contents, memsync_d['p'][-1], generate_pointer_from_bytes(memory_bytes))
				# Append to handle
				memory_handle.append((getattr(pointer.contents, memsync_d['p'][-1]), len(memory_bytes)))

		return memory_handle


	def __adjust_wchar_length__(self, in_bytes, old_len, new_len):

		if old_len == new_len:
			return in_bytes

		elif new_len > old_len:
			tmp = bytearray(len(in_bytes) * new_len // old_len)
			for index in range(old_len):
				tmp[index::new_len] = in_bytes[index::old_len]
			return bytes(tmp)

		else:
			tmp = bytearray(len(in_bytes) * new_len // old_len)
			for index in range(new_len):
				tmp[index::new_len] = in_bytes[index::old_len]
			return bytes(tmp)


	def __get_argument_by_memsync_path__(self, args_tuple, memsync_path):

		# Reference args_tuple as initial value
		element = args_tuple

		# Step through path
		for path_element in memsync_path:

			# Go deeper ... # TODO use __item_pointer_strip__ ?
			if isinstance(path_element, int):
				element = element[path_element]
			else:
				element = getattr(self.__item_pointer_strip__(element), path_element)

		return element


	def __pack_memory_item__(self, args_tuple, memsync_d):

		# Search for pointer
		pointer = self.__get_argument_by_memsync_path__(args_tuple, memsync_d['p'])

		# Is there a function defining the length?
		if '_f' in memsync_d.keys() and isinstance(memsync_d['l'], tuple):

			# Start list for length function arguments
			length_func_arg_list = []

			# Iterate over length components
			for length_component in memsync_d['l']:

				# Append length argument to list
				length_func_arg_list.append(self.__get_argument_by_memsync_path__(args_tuple, length_component))

			# Compute length
			length = memsync_d['_f'](*length_func_arg_list)

		else:

			# Search for length
			length = self.__get_argument_by_memsync_path__(args_tuple, memsync_d['l'])

		# Compute actual length - might come from ctypes or a Python datatype
		length_value = getattr(length, 'value', length) * ctypes.sizeof(memsync_d['_t'])

		# Convert argument into ctypes datatype TODO more checks needed!
		if '_c' in memsync_d.keys():
			arg_value = ctypes.pointer(memsync_d['_c'].from_param(pointer))
		else:
			arg_value = pointer

		# Serialize the data ...
		memory_bytes = serialize_pointer_into_bytes(arg_value, length_value)

		return memory_bytes, arg_value
